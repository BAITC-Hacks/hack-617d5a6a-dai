"""Второй объектив: положение узла относительно кластеров при обычных суммах («тихий мост»).

Скор-редкость (priority) поднимает громких: большие суммы, много контрагентов. Организатор или
площадка обналичивания может переводить мало и ровно и выделяться только положением: касается многих
кластеров или seed-ветвей, но плотно не входит ни в один. Модуль считает такие признаки и флаг
quiet_bridge_flag; проверку «не переупакованная ли это степень» — в отчёте замеров.

Итог проверки 23.09 (редакция 2): флаг — диагностика для README, в скор, роли и карточки не входит.
На обходе только по исходящим положение относительно кластеров не несёт информации сверх степени
и случайного графа с теми же степенями; числа и формулировки — position_section.md.

Вход: nodes/edges/tx из task/data и cluster_map gid -> cluster_id (из outputs/nodes_roles.csv; если
файла нет — слабосвязные компоненты, с предупреждением). Не импортирует backend и другие модули
pipeline/, кроме load.py.

CLI: python -m pipeline.position --data task/data --out outputs [--roles outputs/nodes_roles.csv]
     [--report path.json]   -> <out>/position.csv (+ JSON с рёбрами edge_atypical_for_cluster)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------- пороги (квантили — по task/data 23.09.2026) ----------------
# Редакция 2 (после проверки 23.09): seed-условия убраны из флага, «обычные суммы» требуют ≥ 3 переводов,
# листья последнего колена без исходящих исключены. Причины и числа — в position_section.md.
TYPICAL_Q_LOW = 0.25    # «обычные суммы»: медианный перцентиль сумм переводов узла в [P25; P75]
TYPICAL_Q_HIGH = 0.75   # общего распределения 4 840 переводов (P25 = 12 745, P75 = 80 854 KZT; снизу
                        # усечено порогом выгрузки 5 000, так что P25 смещён вверх)
MIN_TX_TYPICAL = 3      # перцентиль медианы по 1–2 переводам проходит окно в ~55 % случаев сам по себе
                        # (случайное прореживание), поэтому «обычные суммы» — только при ≥ 3 переводах
MIN_CLUSTER_SPREAD = 3  # контрагенты минимум в 3 чужих кластерах
MIN_BOUNDARY_SHARE = 0.5  # ≥ половины оборота по межкластерным рёбрам
MIN_COUNTERPARTIES = 2  # любое условие положения — при ≥ 2 контрагентах (иначе лист с одним чужим входом = 1,0)
TURNOVER_TOP_Q = 0.90   # не в топ-10 % по in_kzt + out_kzt: громких уже поднимает priority
MIN_TX_DATE_REGULARITY = 3  # date_regularity считается при ≥ 3 переводах, иначе NaN
# n_seed_upstream / n_seed_direct во флаг НЕ входят: на обходе только по исходящим они растут с глубиной
# (медиана n_seed_upstream = 7 на глубинах 1–4, «ниже ствола большой компоненты»); n_seed_upstream уже
# седьмое слагаемое SCORE_TERMS в rules.py. Остаются колонками для карточки.
MIN_SEED_DIRECT = 3     # только для диагностического quiet_bridge_strict (редакция 1), не для флага
# избыток разброса над ожидаемым при тех же контрагентах: перестановка меток кластеров внутри
# слабосвязной компоненты, N_EXCESS_PERM повторов, фиксированный seed
N_EXCESS_PERM = 50
EXCESS_SEED = 42
# ребро «обычное по величине, но межкластерное»: sum_kzt и n_tx в [P25; P75] всех 3 119 рёбер
EDGE_Q_LOW, EDGE_Q_HIGH = 0.25, 0.75


def load_cluster_map(roles_csv: Path | None, nodes: pd.DataFrame, edges: pd.DataFrame):
    """cluster_map и n_seed_upstream из nodes_roles.csv; без файла — WCC и собственный расчёт."""
    if roles_csv is not None and Path(roles_csv).exists():
        r = pd.read_csv(roles_csv, usecols=["gid", "cluster_id", "n_seed_upstream"])
        r["gid"] = r.gid.astype("int64")
        return dict(zip(r.gid, r.cluster_id.astype(int))), dict(zip(r.gid, r.n_seed_upstream.astype(int))), "nodes_roles.csv"
    warnings.warn("nodes_roles.csv не найден: кластеры = слабосвязные компоненты, n_seed_upstream считается здесь")
    idx, src, dst = _index(nodes, edges)
    comp = _wcc(len(idx), src, dst)
    return dict(zip(nodes.gid.astype("int64"), comp)), None, "wcc_fallback"


# ---------------- вспомогательное ----------------
def _index(nodes, edges):
    gids = nodes.gid.astype("int64").to_numpy()
    pos = pd.Series(np.arange(len(gids)), index=gids)
    return gids, pos.loc[edges.src.to_numpy()].to_numpy(), pos.loc[edges.dst.to_numpy()].to_numpy()


def _wcc(n, src, dst):
    parent = np.arange(n)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in zip(src, dst):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    return pd.factorize(roots)[0]


def _seed_reach(n, src, dst, seed_idx, block_other_seeds: bool) -> np.ndarray:
    """bool-матрица [узел, seed]: узел достижим от seed по исходящим (сам seed не считается).
    block_other_seeds=True: обход не продолжается из других seed (независимая ветвь)."""
    out = [[] for _ in range(n)]
    for a, b in zip(src, dst):
        out[a].append(b)
    is_seed = np.zeros(n, bool)
    is_seed[seed_idx] = True
    M = np.zeros((n, len(seed_idx)), bool)
    for j, s in enumerate(seed_idx):
        seen = {s}
        q = deque([s])
        while q:
            u = q.popleft()
            if block_other_seeds and u != s and is_seed[u]:
                continue
            for v in out[u]:
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        seen.discard(s)
        M[list(seen), j] = True
    return M


def _n_unique_pairs(owner, other_cl, own_cl, n):
    """Сколько разных чужих кластеров other_cl у каждого owner (own_cl — кластер owner)."""
    m = other_cl != own_cl
    if not m.any():
        return np.zeros(n, int)
    K = int(max(other_cl.max(), own_cl.max())) + 1
    key = np.unique(owner[m].astype(np.int64) * K + other_cl[m])
    return np.bincount((key // K).astype(int), minlength=n)


class _Prepared:
    """Всё, что не зависит от разметки кластеров (для 200 перестановок в нулях)."""

    def __init__(self, nodes, edges, tx, n_seed_upstream=None):
        self.gids, self.src, self.dst = _index(nodes, edges)
        self.n = n = len(self.gids)
        self.w = edges.sum_kzt.to_numpy(float)
        self.ntx = edges.n_tx.to_numpy(int)
        self.depth = nodes.depth.to_numpy(int)
        self.is_seed = nodes.is_seed.to_numpy(bool)
        self.seed_idx = np.flatnonzero(self.is_seed)
        # уникальные неориентированные пары контрагентов
        a, b = np.minimum(self.src, self.dst), np.maximum(self.src, self.dst)
        pairs = np.unique(np.stack([a, b], 1), axis=0)
        self.pu, self.pv = pairs[:, 0], pairs[:, 1]
        self.n_cp = np.bincount(np.r_[self.pu, self.pv], minlength=n)
        self.turnover = np.bincount(self.src, self.w, n) + np.bincount(self.dst, self.w, n)
        self.in_deg = np.bincount(self.dst, minlength=n)
        self.out_deg = np.bincount(self.src, minlength=n)
        self.M_all = _seed_reach(n, self.src, self.dst, self.seed_idx, block_other_seeds=False)
        self.M_dir = _seed_reach(n, self.src, self.dst, self.seed_idx, block_other_seeds=True)
        self.n_seed_upstream = (np.array([n_seed_upstream.get(int(g), 0) for g in self.gids])
                                if n_seed_upstream else self.M_all.sum(1))
        self.n_seed_direct = self.M_dir.sum(1)
        # суммы переводов: перцентиль в общем распределении 4 840 переводов
        pos = pd.Series(np.arange(n), index=self.gids)
        pct = tx.sum_kzt.rank(pct=True, method="average").to_numpy()
        t = pd.DataFrame({
            "node": np.r_[pos.loc[tx.src].to_numpy(), pos.loc[tx.dst].to_numpy()],
            "pct": np.r_[pct, pct],
            "amt": np.r_[tx.sum_kzt.to_numpy(), tx.sum_kzt.to_numpy()],
            "date": np.r_[tx.date.to_numpy(), tx.date.to_numpy()],
        })
        g = t.groupby("node")
        self.amount_typicality = g.pct.median().reindex(range(n)).to_numpy()
        self.n_transfers = g.size().reindex(range(n)).fillna(0).astype(int).to_numpy()
        rep = t.assign(dup=t.duplicated(["node", "amt"], keep=False)).groupby("node").dup.mean()
        self.amount_regularity = rep.reindex(range(n)).to_numpy()
        cv = g.amt.agg(lambda s: s.std(ddof=0) / s.mean() if len(s) >= 2 and s.mean() > 0 else np.nan)
        self.amount_cv = cv.reindex(range(n)).to_numpy()
        self.amount_median = g.amt.median().reindex(range(n)).to_numpy()
        self.date_regularity = self._date_regularity(t).reindex(range(n)).to_numpy()
        self.amount_typicality = np.where(self.n_transfers >= MIN_TX_TYPICAL, self.amount_typicality, np.nan)
        self.typical = (self.amount_typicality >= TYPICAL_Q_LOW) & (self.amount_typicality <= TYPICAL_Q_HIGH)
        # лист последнего колена без исходящих: исходящие не выгружались, «0 чужих получателей» не наблюдение
        self.max_depth = int(self.depth.max())
        self.unobserved_out = (self.depth == self.max_depth) & (self.out_deg == 0)
        self.wcc = _wcc(n, self.src, self.dst)
        self.not_loud = self.turnover < np.quantile(self.turnover, TURNOVER_TOP_Q)
        # рёбра обычной величины (для edge_atypical_for_cluster)
        lo_w, hi_w = np.quantile(self.w, [EDGE_Q_LOW, EDGE_Q_HIGH])
        lo_n, hi_n = np.quantile(self.ntx, [EDGE_Q_LOW, EDGE_Q_HIGH])
        self.edge_ordinary = (self.w >= lo_w) & (self.w <= hi_w) & (self.ntx >= lo_n) & (self.ntx <= hi_n)
        self.edge_bounds = {"sum_kzt": [float(lo_w), float(hi_w)], "n_tx": [float(lo_n), float(hi_n)]}

    @staticmethod
    def _date_regularity(t):
        """max(доля переводов в модальный день недели, доля шагов между датами, равных модальному шагу)."""
        def f(d):
            if len(d) < MIN_TX_DATE_REGULARITY:
                return np.nan
            d = pd.to_datetime(pd.Series(d)).sort_values()
            wd = d.dt.dayofweek.value_counts(normalize=True).iloc[0]
            gaps = d.drop_duplicates().diff().dt.days.dropna()
            step = gaps.value_counts(normalize=True).iloc[0] if len(gaps) >= 2 else 0.0
            return float(max(wd, step))
        return t.groupby("node").date.agg(f)

    def compute(self, c: np.ndarray, full: bool = True):
        """c — cluster_id по индексу узла. full=False: только то, что нужно для флагов (для нулей)."""
        n, src, dst = self.n, self.src, self.dst
        cs, cd = c[src], c[dst]
        spread_in = _n_unique_pairs(dst, cs, cd, n)
        spread_out = _n_unique_pairs(src, cd, cs, n)
        spread = _n_unique_pairs(np.r_[self.pu, self.pv], np.r_[c[self.pv], c[self.pu]],
                                 np.r_[c[self.pu], c[self.pv]], n)
        cross = cs != cd
        cross_kzt = np.bincount(src[cross], self.w[cross], n) + np.bincount(dst[cross], self.w[cross], n)
        with np.errstate(invalid="ignore", divide="ignore"):
            boundary = np.where(self.turnover > 0, cross_kzt / self.turnover, np.nan)
        # seed_lineage_spread: сколько разных кластеров среди seed, чьи ветви содержат узел
        K = int(c.max()) + 1
        onehot = np.zeros((len(self.seed_idx), K), bool)
        onehot[np.arange(len(self.seed_idx)), c[self.seed_idx]] = True
        lineage = ((self.M_all.astype(np.int32) @ onehot.astype(np.int32)) > 0).sum(1)
        lineage_dir = ((self.M_dir.astype(np.int32) @ onehot.astype(np.int32)) > 0).sum(1)
        pos_cond = (self.n_cp >= MIN_COUNTERPARTIES) & (
            (spread >= MIN_CLUSTER_SPREAD) | (np.nan_to_num(boundary) >= MIN_BOUNDARY_SHARE))
        flag = self.typical & pos_cond & self.not_loud & ~self.unobserved_out
        pos_strict = (self.n_cp >= MIN_COUNTERPARTIES) & (
            (spread >= MIN_CLUSTER_SPREAD) | (self.n_seed_direct >= MIN_SEED_DIRECT)
            | (np.nan_to_num(boundary) >= MIN_BOUNDARY_SHARE))
        strict = self.typical & pos_strict & self.not_loud
        edge_atyp = self.edge_ordinary & cross
        res = {"quiet_bridge_flag": flag, "quiet_bridge_strict": strict, "edge_atypical": edge_atyp,
               "cluster_spread": spread, "boundary_share": boundary}
        if not full:
            return res
        xp = (c[self.pu] != c[self.pv]).astype(float)
        cp_cross = np.bincount(np.r_[self.pu, self.pv], np.r_[xp, xp], n)
        with np.errstate(invalid="ignore", divide="ignore"):
            intra = np.where(self.n_cp > 0, 1 - cp_cross / np.maximum(self.n_cp, 1), np.nan)
        # нули вместо «нет данных»: узлы без контрагентов (19 seed без рёбер) и исходящая сторона листьев
        # последнего колена — NaN, а не 0
        none = self.n_cp == 0
        f = lambda x: np.where(none, np.nan, x.astype(float))
        spread_out = np.where(self.unobserved_out, np.nan, f(spread_out))
        res.update(cluster_spread_in=f(spread_in), cluster_spread_out=spread_out, intra_density=intra,
                   seed_lineage_spread=lineage, seed_lineage_spread_direct=lineage_dir,
                   cluster_spread_excess=self.spread_excess(c, spread))
        res["cluster_spread"] = f(spread)
        return res

    def spread_excess(self, c: np.ndarray, spread: np.ndarray) -> np.ndarray:
        """cluster_spread минус его среднее при перестановке меток внутри слабосвязной компоненты:
        сравнение узла с самим собой при тех же контрагентах (степень учтена по построению)."""
        rng = np.random.default_rng(EXCESS_SEED)
        groups = [np.flatnonzero(self.wcc == k) for k in np.unique(self.wcc)]
        groups = [g for g in groups if len(g) > 1]
        both = np.r_[self.pu, self.pv]
        acc = np.zeros(self.n)
        for _ in range(N_EXCESS_PERM):
            cc = c.copy()
            for g in groups:
                cc[g] = rng.permutation(c[g])
            acc += _n_unique_pairs(both, np.r_[cc[self.pv], cc[self.pu]], np.r_[cc[self.pu], cc[self.pv]], self.n)
        return np.where(self.n_cp == 0, np.nan, spread - acc / N_EXCESS_PERM)


def _frame(p: _Prepared, c: np.ndarray, r: dict) -> pd.DataFrame:
    return pd.DataFrame({
        "gid": p.gids, "cluster_id": c, "depth": p.depth, "is_seed": p.is_seed,
        "n_counterparties": p.n_cp, "in_deg": p.in_deg, "out_deg": p.out_deg, "turnover_kzt": p.turnover,
        "cluster_spread_in": r["cluster_spread_in"], "cluster_spread_out": r["cluster_spread_out"],
        "cluster_spread": r["cluster_spread"], "cluster_spread_excess": r["cluster_spread_excess"],
        "boundary_share": r["boundary_share"],
        "intra_density": r["intra_density"],
        "n_seed_upstream": p.n_seed_upstream, "n_seed_direct": p.n_seed_direct,
        "seed_lineage_spread": r["seed_lineage_spread"], "seed_lineage_spread_direct": r["seed_lineage_spread_direct"],
        "n_transfers": p.n_transfers, "amount_median_kzt": p.amount_median,
        "amount_typicality": p.amount_typicality, "amount_regularity": p.amount_regularity,
        "amount_cv": p.amount_cv, "date_regularity": p.date_regularity,
        "quiet_bridge_flag": r["quiet_bridge_flag"], "quiet_bridge_strict": r["quiet_bridge_strict"],
    })


def position_features(nodes_df, edges_df, tx_df, cluster_map: dict, n_seed_upstream: dict | None = None,
                      _return_prepared: bool = False):
    """DataFrame по всем узлам nodes_df (gid). n_seed_upstream: dict gid->int из nodes_roles.csv
    (None — считается здесь обходом по исходящим от seed, как в features.py)."""
    p = _Prepared(nodes_df, edges_df, tx_df, n_seed_upstream)
    c = np.array([int(cluster_map[int(g)]) for g in p.gids])
    r = p.compute(c)
    df = _frame(p, c, r)
    if _return_prepared:
        return df, p, c, r
    return df


def atypical_edges(edges_df: pd.DataFrame, p: _Prepared, r: dict) -> list[dict]:
    e = edges_df.loc[r["edge_atypical"], ["src", "dst", "sum_kzt", "n_tx"]]
    return [{"src": str(a), "dst": str(b), "sum_kzt": float(s), "n_tx": int(k)} for a, b, s, k in e.itertuples(index=False)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default="task/data")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--roles", default=None, help="nodes_roles.csv (по умолчанию <out>/nodes_roles.csv)")
    ap.add_argument("--report", default=None)
    a = ap.parse_args(argv)
    from .load import load
    t0 = time.perf_counter()
    edges, nodes, tx = load(Path(a.data))
    roles = Path(a.roles) if a.roles else Path(a.out) / "nodes_roles.csv"
    cmap, nsu, src = load_cluster_map(roles, nodes, edges)
    df, p, c, r = position_features(nodes, edges, tx, cmap, nsu, _return_prepared=True)
    el = time.perf_counter() - t0
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    df.assign(gid=df.gid.astype(str)).to_csv(out / "position.csv", index=False)
    rep = {"elapsed_s": round(el, 3), "cluster_source": src, "n_nodes": int(len(df)),
           "n_quiet_bridge": int(df.quiet_bridge_flag.sum()), "n_quiet_bridge_strict": int(df.quiet_bridge_strict.sum()),
           "thresholds": {"typical_q": [TYPICAL_Q_LOW, TYPICAL_Q_HIGH], "min_tx_typical": MIN_TX_TYPICAL,
                          "min_cluster_spread": MIN_CLUSTER_SPREAD, "min_boundary_share": MIN_BOUNDARY_SHARE,
                          "min_counterparties": MIN_COUNTERPARTIES, "turnover_top_q": TURNOVER_TOP_Q,
                          "excluded": f"depth == {p.max_depth} & out_deg == 0"},
           "integration": "readme-only: во скор, роли и карточки не входит (см. position_section.md)",
           "edge_ordinary_bounds": p.edge_bounds,
           "edge_atypical_for_cluster_note": ("диагностика, НЕ для экрана: межкластерных рёбер обычной величины в "
                                              "реальном графе меньше, чем в случайном с теми же степенями"),
           "edge_atypical_for_cluster": atypical_edges(edges, p, r)}
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"position: {len(df)} узлов, quiet_bridge {rep['n_quiet_bridge']} (строгий {rep['n_quiet_bridge_strict']}), "
          f"межкластерных обычных рёбер {len(rep['edge_atypical_for_cluster'])}, {el:.2f} с", file=sys.stderr)


if __name__ == "__main__":
    main()
