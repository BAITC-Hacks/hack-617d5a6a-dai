"""Проверка качества выгрузок «Граф денег» без разметки.

Запуск из корня репозитория:

    python -m pipeline.metrics --data task/data --out outputs --report outputs/metrics.json \
        [--perm 1000] [--seed 42] [--compare <второй каталог с CSV>] [--temporal-impl pipeline|own]

Модуль не импортирует backend и не зависит от того, как получены CSV: на вход идут три parquet
организаторов и три CSV схемы ТЗ (nodes_roles.csv, clusters.csv, top_nodes.csv), по желанию
run_meta.json рядом с ними. Определения, пороги и куда отчитывается каждая метрика:
docs/ds_metrics_2026-09-23.md. Имена признаков и колонок, их синонимы в других документах и маски —
глоссарий docs/ds_system_design_2026-09-23.md §8: здесь имена такие же, как в CSV пайплайна
(in_kzt, out_kzt, pass_kzt, pass_through), а не in_sum_kzt/out_sum_kzt из related_work.

Каждая проверка возвращает {name, ok, value, threshold, note} плюс group и required.
ok = True / False / None (None — информационная метрика или проверка не запускалась).
Код возврата 1, если провалена хотя бы одна обязательная проверка (required=True). Отчёт пишется
всегда, в том числе при падении модуля (проверка metrics_crash).

Эталон приоритета не реализован здесь заново: priority_raw, n_terms_above_p95 и in_queue
пересчитываются вызовом функций пайплайна (load.load → features.compute → run._temporal_features →
priority.v1) и сверяются с CSV, чтобы формула в двух местах не разъезжалась. На том же эталоне
считаются шум ±5 % и ablation. Чувствительность ролей к порогам — на правилах заглушки v0 (note).
Перестановочный контроль — pipeline.temporal_check.run_check (--temporal-impl own — своя
реализация). Сравнение с dummy — pipeline.baselines.run_baselines, результат в ключе "baselines".
Модуль ничего не пишет, кроме файла --report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import connected_components
from scipy.special import gammaln

ROLES = ("consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral")
NODE_COLS = ("gid", "role", "role_score", "cluster_id", "priority_score", "evidence")
CLUSTER_COLS = ("cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis")
TOP_COLS = ("rank", "gid", "role", "priority_score", "why")
EVIDENCE_MAX = 200
TOP_MIN = 20
KZT_TOL = 1.0  # KZT, допуск на суммы кластеров при сверке с parquet
BOUNDARY_WORDS = ("depth=4", "depth 4", "глубин", "границ", "колен", "обрыв", "выгрузк")

# быстрый транзит (docs/hypothesis_check_2026-09-23.md, план §4.3)
FT_LAG = (0, 2)          # дней, день выхода − день входа
FT_RATIO = (0.8, 1.2)    # выход / вход
FT_MIN_PAIRS = 2

QUEUE_MIN_TERMS_DEFAULT = 2      # rules.QUEUE_MIN_TERMS_ABOVE_P95; читается из run_meta

GID_RE = re.compile(r"^\d{1,19}$")
DIGIT_RE = re.compile(r"\d")
INT64_MAX = 2 ** 63


# ============================================================ служебное

class Report:
    def __init__(self):
        self.checks: list[dict] = []
        self.timing: dict[str, float] = {}
        self.inputs: dict[str, str] = {}
        self._t = time.perf_counter()

    def add(self, name, ok, value, threshold=None, note="", required=True, group="b"):
        self.checks.append({
            "group": group, "name": name, "required": bool(required),
            "ok": None if ok is None else bool(ok),
            "value": _jsonable(value), "threshold": _jsonable(threshold), "note": note,
        })

    def stage(self, name):
        now = time.perf_counter()
        self.timing[name] = round(now - self._t, 3)
        self._t = now


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if math.isnan(v) else round(v, 6)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if x is pd.NA:
        return None
    return x


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================ загрузка

def load_data(data_dir: Path):
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    edges = pd.read_parquet(data_dir / "edges.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    nodes = nodes.sort_values("gid").reset_index(drop=True)
    gids = nodes.gid.to_numpy(np.int64)
    pos = pd.Series(np.arange(len(gids)), index=gids)
    e = edges.copy()
    e["s"] = pos.reindex(e.src.to_numpy()).to_numpy()
    e["d"] = pos.reindex(e.dst.to_numpy()).to_numpy()
    t = tx.copy()
    t["s"] = pos.reindex(t.src.to_numpy()).to_numpy()
    t["d"] = pos.reindex(t.dst.to_numpy()).to_numpy()
    # абсолютный номер дня: переход через границу месяца даёт верный лаг
    t["day"] = (pd.to_datetime(t.date).dt.normalize() - pd.Timestamp("1970-01-01")).dt.days.astype(int)
    n = len(gids)
    feat = pd.DataFrame({"gid": gids, "depth": nodes.depth.to_numpy(), "is_seed": nodes.is_seed.to_numpy(bool)})
    feat["in_deg"] = np.bincount(e.d, minlength=n)
    feat["out_deg"] = np.bincount(e.s, minlength=n)
    feat["in_kzt"] = np.bincount(e.d, weights=e.sum_kzt, minlength=n)
    feat["out_kzt"] = np.bincount(e.s, weights=e.sum_kzt, minlength=n)
    feat["in_tx"] = np.bincount(e.d, weights=e.n_tx, minlength=n).astype(int)
    feat["out_tx"] = np.bincount(e.s, weights=e.n_tx, minlength=n).astype(int)
    feat["truncated"] = (feat.depth == 4) & (feat.out_deg == 0)
    return feat, e, t


def build_graphs(feat, e):
    gids = feat.gid.tolist()
    G = nx.DiGraph()
    G.add_nodes_from(range(len(gids)))
    G.add_edges_from(zip(e.s.tolist(), e.d.tolist()))
    U = nx.Graph()
    U.add_nodes_from(range(len(gids)))
    for s, d, w in zip(e.s.tolist(), e.d.tolist(), e.sum_kzt.tolist()):
        if U.has_edge(s, d):
            U[s][d]["weight"] += w
        else:
            U.add_edge(s, d, weight=w)
    return G, U


def read_csv_str(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def parse_gid(col: pd.Series):
    """gid строкой → Int64 без прохода через float; битые строки и переполнение int64 дают NA."""
    s = col.astype(str).str.strip()
    good = s.map(lambda x: bool(GID_RE.match(x)) and int(x) < INT64_MAX)
    vals = pd.array([int(x) if g else pd.NA for x, g in zip(s, good)], dtype="Int64")
    return good, pd.Series(vals, index=col.index)


def parse_bool(col: pd.Series) -> pd.Series:
    m = {"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0, "1.0": 1.0, "0.0": 0.0}
    return col.astype(str).str.strip().str.lower().map(m)


# ============================================================ разбиения: AMI / ARI

def _contingency(a, b):
    _, ai = np.unique(a, return_inverse=True)
    _, bi = np.unique(b, return_inverse=True)
    m = sparse.coo_matrix((np.ones(len(ai)), (ai, bi))).tocsr()
    m.sum_duplicates()
    return m


def ari(a, b) -> float:
    m = _contingency(a, b)
    n = len(a)
    c2 = lambda x: x * (x - 1) / 2.0
    sij = c2(m.data).sum()
    sa = c2(np.asarray(m.sum(1)).ravel()).sum()
    sb = c2(np.asarray(m.sum(0)).ravel()).sum()
    exp = sa * sb / c2(n)
    mx = (sa + sb) / 2.0
    return 1.0 if mx == exp else float((sij - exp) / (mx - exp))


def _emi(av, bv, n) -> float:
    """Ожидаемая взаимная информация (Vinh и др., 2010), с кэшем по парам размеров."""
    cache: dict[tuple[int, int], float] = {}
    lg_n = gammaln(n + 1)
    total = 0.0
    for a in av:
        for b in bv:
            key = (a, b) if a <= b else (b, a)
            if key not in cache:
                lo, hi = max(1, a + b - n), min(a, b)
                if lo > hi:
                    cache[key] = 0.0
                else:
                    nij = np.arange(lo, hi + 1, dtype=float)
                    term1 = nij / n * (np.log(nij * n) - np.log(a * b))
                    lg = (gammaln(a + 1) + gammaln(b + 1) + gammaln(n - a + 1) + gammaln(n - b + 1)
                          - lg_n - gammaln(nij + 1) - gammaln(a - nij + 1) - gammaln(b - nij + 1)
                          - gammaln(n - a - b + nij + 1))
                    cache[key] = float((term1 * np.exp(lg)).sum())
            total += cache[key]
    return total


def ami(a, b) -> float:
    m = _contingency(a, b)
    n = len(a)
    av = np.asarray(m.sum(1)).ravel().astype(int)
    bv = np.asarray(m.sum(0)).ravel().astype(int)
    if len(av) == len(bv) == 1 or len(av) == len(bv) == n:
        return 1.0
    nij = m.data
    rows, cols = m.nonzero()
    mi = float((nij / n * (np.log(nij * n) - np.log(av[rows] * bv[cols]))).sum())
    h = lambda v: float(-(v / n * np.log(v / n)).sum())
    ha, hb = h(av), h(bv)
    emi = _emi(av.tolist(), bv.tolist(), n)
    den = (ha + hb) / 2.0 - emi
    return float((mi - emi) / den) if den > 1e-12 else 1.0


def louvain_labels(U: nx.Graph, seed: int, resolution: float = 1.0) -> np.ndarray:
    """Louvain на U + разделение несвязных сообществ (как в спецификации кластеров)."""
    comms = nx.community.louvain_communities(U, weight="weight", resolution=resolution, seed=seed)
    parts = []
    for c in comms:
        sub = U.subgraph(c)
        parts.extend(nx.connected_components(sub) if not nx.is_connected(sub) else [c])
    parts.sort(key=lambda c: (-len(c), min(c)))
    lab = np.empty(U.number_of_nodes(), dtype=int)
    for i, c in enumerate(parts):
        lab[list(c)] = i
    return lab


def modularity(U: nx.Graph, lab: np.ndarray) -> float:
    parts = [set(np.flatnonzero(lab == c).tolist()) for c in np.unique(lab)]
    return float(nx.community.modularity(U, parts, weight="weight"))


# ============================================================ быстрый транзит и перестановки

class FastTransit:
    """Пары «вход A→B, выход B→C» с A≠C и отношением сумм 0,8–1,2; окно лага 0–2 дня.

    Флаг узла B: существует сопоставление 1-к-1 из ≥2 пар (ни один перевод не используется дважды).
    Для двудольного графа «входы × выходы» это равносильно: среди допустимых пар ≥2 разных входа
    и ≥2 разных выхода (паросочетание размера 1 бывает только у звезды). Число пар для отчёта
    считается жадно в порядке плана §4.3: |отношение − 1|, затем |лаг|.
    """

    def __init__(self, t: pd.DataFrame, n_nodes: int, amounts: np.ndarray | None = None):
        self.n = n_nodes
        self.t = t
        self.amt = t.sum_kzt.to_numpy(float) if amounts is None else amounts
        self.days = t.day.to_numpy(int)
        idx = np.arange(len(t))
        tin = pd.DataFrame({"i": idx, "b": t.d.to_numpy(), "a": t.s.to_numpy()})
        tout = pd.DataFrame({"o": idx, "b": t.s.to_numpy(), "c": t.d.to_numpy()})
        m = tin.merge(tout, on="b")
        m = m[m.a != m.c]
        r = self.amt[m.o.to_numpy()] / self.amt[m.i.to_numpy()]
        keep = (r >= FT_RATIO[0]) & (r <= FT_RATIO[1])
        m = m[keep]
        self.pi = m.i.to_numpy()
        self.po = m.o.to_numpy()
        self.pb = m.b.to_numpy()
        self.pr = np.abs(r[keep] - 1.0)

    def flags(self, days: np.ndarray | None = None) -> np.ndarray:
        d = self.days if days is None else days
        lag = d[self.po] - d[self.pi]
        ok = (lag >= FT_LAG[0]) & (lag <= FT_LAG[1])
        b, i, o = self.pb[ok], self.pi[ok], self.po[ok]
        if len(b) == 0:
            return np.zeros(self.n, dtype=bool)
        m = len(d)
        ni = np.bincount(np.unique(b.astype(np.int64) * m + i) // m, minlength=self.n)
        no = np.bincount(np.unique(b.astype(np.int64) * m + o) // m, minlength=self.n)
        return (ni >= FT_MIN_PAIRS) & (no >= FT_MIN_PAIRS)

    def greedy_pairs(self) -> np.ndarray:
        lag = self.days[self.po] - self.days[self.pi]
        ok = (lag >= FT_LAG[0]) & (lag <= FT_LAG[1])
        df = pd.DataFrame({"b": self.pb[ok], "i": self.pi[ok], "o": self.po[ok],
                           "r": self.pr[ok], "lag_abs": np.abs(lag[ok])})
        df = df.sort_values(["b", "r", "lag_abs", "i", "o"])
        cnt = np.zeros(self.n, dtype=int)
        used_i, used_o = set(), set()
        for b, i, o in zip(df.b.to_numpy(), df.i.to_numpy(), df.o.to_numpy()):
            if i in used_i or o in used_o:
                continue
            used_i.add(i)
            used_o.add(o)
            cnt[b] += 1
        return cnt


def permutation_test(ft: FastTransit, t: pd.DataFrame, n_perm: int, seed: int) -> dict:
    """Два нуля: глобальная перестановка дат и перестановка дат внутри отправителя."""
    rng = np.random.default_rng(seed)
    obs = int(ft.flags().sum())
    days = ft.days
    src = t.s.to_numpy()
    base = np.argsort(src, kind="stable")
    res = {"observed": obs, "n_perm": n_perm, "seed": seed}
    for name in ("global", "within_sender"):
        null = np.empty(n_perm, dtype=int)
        for k in range(n_perm):
            if name == "global":
                nd = rng.permutation(days)
            else:
                order = np.lexsort((rng.random(len(days)), src))
                nd = np.empty_like(days)
                nd[base] = days[order]
            null[k] = int(ft.flags(nd).sum())
        res[name] = {
            "mean": float(null.mean()), "sd": float(null.std(ddof=1)) if n_perm > 1 else None,
            "p": float((1 + (null >= obs).sum()) / (n_perm + 1)),
        }
    return res


# ============================================================ эталон приоритета через пайплайн и правила v0

def pipeline_reference(data_dir: Path, tx_noise: np.ndarray | None = None) -> pd.DataFrame:
    """Признаки и priority.v1 функциями пайплайна; строки по возрастанию gid (как feat).

    tx_noise — множители сумм переводов (по строкам transactions.parquet после load.load): суммы
    рёбер, pass_kzt и флаг быстрого транзита пересчитываются, степени и betweenness берутся как есть."""
    from pipeline import features as pf, load as pl, priority as pp
    from pipeline.run import _temporal_features
    edges, nodes, tx = pl.load(data_dir)
    g = pf.build_graph(edges, nodes)
    df = pf.compute(g, nodes, tx)
    tf, _ = _temporal_features(tx, nodes)
    df = df.merge(tf, on="gid", how="left", validate="one_to_one")
    return pp.v1(df.sort_values("gid").reset_index(drop=True))


def reference_with_noise(base: pd.DataFrame, data_dir: Path, rng: np.random.Generator) -> pd.DataFrame:
    """Шум U(0,95; 1,05) на каждый перевод; пересчёт сумм, pass_kzt, быстрого транзита и priority.v1."""
    from pipeline import load as pl, priority as pp
    from pipeline.run import _temporal_features
    _, nodes, tx = pl.load(data_dir)
    tx = tx.assign(sum_kzt=tx.sum_kzt.to_numpy() * rng.uniform(0.95, 1.05, len(tx)))
    df = base.drop(columns=[c for c in base.columns if c.startswith(("p_", "c_")) or c in
                            ("priority_raw", "priority_score", "score_terms", "n_terms_above_p95", "in_queue",
                             "fast_transit_pairs", "fast_transit_flag", "has_reversed_pair", "has_same_day_pair")])
    ins = tx.groupby("dst").sum_kzt.sum()
    outs = tx.groupby("src").sum_kzt.sum()
    df["in_kzt"] = df.gid.map(ins).fillna(0.0).to_numpy()
    df["out_kzt"] = df.gid.map(outs).fillna(0.0).to_numpy()
    df["pass_kzt"] = np.minimum(df.in_kzt, df.out_kzt)
    df.loc[df.depth4_boundary | df.isolated, "pass_kzt"] = 0.0
    tf, _ = _temporal_features(tx, nodes)
    df = df.merge(tf, on="gid", how="left", validate="one_to_one")
    return pp.v1(df)


def topk(score: np.ndarray, gids: np.ndarray, k: int) -> np.ndarray:
    order = np.lexsort((gids, -score))
    return order[:k]


def ablation_top20(terms: dict, flag: np.ndarray, flag_w: float, gids: np.ndarray, base_top: set) -> dict:
    """Пересечение топ-20 эталона с топ-20 без каждого слагаемого по очереди."""
    S = sum(terms.values()) + flag_w * flag
    out = {k: len(base_top & set(topk(S - v, gids, 20).tolist())) / 20 for k, v in terms.items()}
    out["fast_transit_flag"] = len(base_top & set(topk(S - flag_w * flag, gids, 20).tolist())) / 20
    return out


V0_THRESHOLDS = {"coord_in": 3.0, "coord_out": 5.0, "dist_out": 10.0, "cons_in": 3.0, "transit_band": 0.2}


def roles_v0(feat: pd.DataFrame, th: dict) -> np.ndarray:
    """Правила заглушки v0 (порядок выбора сверху вниз)."""
    i, o = feat.in_deg.to_numpy(float), feat.out_deg.to_numpy(float)
    ik, ok_ = feat.in_kzt.to_numpy(), feat.out_kzt.to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(ik > 0, ok_ / ik, np.nan)
    band = th["transit_band"]
    conds = [
        (i >= th["coord_in"]) & (o >= th["coord_out"]),
        o >= th["dist_out"],
        i >= th["cons_in"],
        (ik > 0) & (ok_ > 0) & (np.abs(ratio - 1) <= band + 1e-12),
        (i > 0) & (o == 0) & (feat.depth.to_numpy() < 4),
    ]
    return np.select(conds, ["coordinator", "distributor", "consolidator", "transit", "terminal"], "peripheral")


QUANT_LADDER = (0.50, 0.75, 0.90, 0.95, 0.975, 0.99, 0.995)


def _ladder_shift(values: np.ndarray, thr: float, step: int) -> float:
    """Сдвиг порога на соседнюю ступень лестницы квантилей (без повторов значений)."""
    lad = sorted(set(float(x) for x in np.quantile(values, QUANT_LADDER)))
    lad = sorted(set(lad) | {thr})
    k = lad.index(thr) + step
    return lad[min(max(k, 0), len(lad) - 1)]


# ============================================================ изъятие топ-N

def removal_curve(e: pd.DataFrame, n: int, removed: np.ndarray, total: float) -> tuple[int, float]:
    alive = np.ones(n, dtype=bool)
    alive[removed] = False
    m = alive[e.s.to_numpy()] & alive[e.d.to_numpy()]
    s, d = e.s.to_numpy()[m], e.d.to_numpy()[m]
    A = sparse.coo_matrix((np.ones(len(s)), (s, d)), shape=(n, n))
    _, lab = connected_components(A, directed=True, connection="weak")
    lab = lab[alive]
    lcc = int(np.bincount(lab).max()) if len(lab) else 0
    return lcc, float(e.sum_kzt.to_numpy()[m].sum() / total)


# ============================================================ основная проверка

def run(data_dir: Path, out_dir: Path, n_perm: int, seed: int, compare: Path | None,
        temporal_impl: str = "pipeline", R: Report | None = None) -> Report:
    R = R if R is not None else Report()
    feat, e, t = load_data(data_dir)
    n = len(feat)
    n_seed_total = int(feat.is_seed.sum())
    total_kzt = float(e.sum_kzt.sum())
    gids = feat.gid.to_numpy(np.int64)
    pos = pd.Series(np.arange(n), index=gids)
    R.stage("load_parquet")

    G, U = build_graphs(feat, e)
    R.stage("build_graphs")

    # ---------------------------------------------------------------- схема CSV
    paths = {k: out_dir / f"{k}.csv" for k in ("nodes_roles", "clusters", "top_nodes")}
    missing = [str(p) for p in paths.values() if not p.exists()]
    if missing:
        R.add("files_present", False, missing, "3 CSV", "нет файлов выгрузки")
        return R
    R.add("files_present", True, {k: sha256(p)[:16] for k, p in paths.items()}, "3 CSV",
          "sha256 (первые 16 знаков) — полные хеши в inputs")
    frames, errs = {}, {}
    for k in ("nodes_roles", "clusters", "top_nodes"):
        try:
            frames[k] = read_csv_str(paths[k])
        except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
            errs[k] = f"{type(exc).__name__}: {exc}"[:200]
    R.add("csv_parse", not errs, errs or "все 3 читаются", "CSV читается",
          "лишняя запятая без кавычек, пустой файл или не UTF-8")
    if errs:
        return R
    nr, cl, tp = frames["nodes_roles"], frames["clusters"], frames["top_nodes"]

    def schema(df, cols, name):
        miss = [c for c in cols if c not in df.columns]
        extra = [c for c in df.columns if c not in cols]
        R.add(f"schema_{name}_columns", not miss, {"missing": miss, "extra": extra}, list(cols),
              "лишние колонки допустимы")
        return not miss

    ok_nr = schema(nr, NODE_COLS, "nodes_roles")
    ok_cl = schema(cl, CLUSTER_COLS, "clusters")
    ok_tp = schema(tp, TOP_COLS, "top_nodes")
    if not (ok_nr and ok_cl and ok_tp):
        return R

    good, nr_gid = parse_gid(nr.gid)
    bad_num = {}
    nr_rs = pd.to_numeric(nr.role_score, errors="coerce")
    nr_ps = pd.to_numeric(nr.priority_score, errors="coerce")
    nr_cid_raw = pd.to_numeric(nr.cluster_id, errors="coerce")
    nr_cid = nr_cid_raw.where(nr_cid_raw % 1 == 0)
    bad_num["gid_not_int64"] = int((~good).sum())
    bad_num["role_score_nan"] = int(nr_rs.isna().sum())
    bad_num["priority_score_nan"] = int(nr_ps.isna().sum())
    bad_num["cluster_id_nan_or_nonint"] = int(nr_cid.isna().sum())
    val = dict(bad_num)
    val["gid_examples"] = nr.gid[~good].head(3).tolist()
    R.add("schema_nodes_roles_dtypes", sum(bad_num.values()) == 0, val, "все 0",
          "gid — целое без знака ≤19 цифр в пределах int64, читается строкой без float; скоры — числа; "
          "cluster_id — целое")

    # ---------------------------------------------------------------- покрытие и уникальность
    g_set = set(nr_gid.dropna().astype("int64").tolist())
    ref = set(gids.tolist())
    R.add("coverage_nodes", len(nr) == n and g_set == ref,
          {"rows": len(nr), "missing": len(ref - g_set), "unknown": len(g_set - ref)}, n,
          "строки nodes_roles.csv против nodes.parquet")
    n_dup = int(nr_gid.dropna().duplicated().sum())
    R.add("gid_unique", n_dup == 0, n_dup, 0, "дубли gid")

    nr = nr.assign(gid_i=nr_gid, role_score_f=nr_rs, priority_f=nr_ps, cid=nr_cid)
    nr = nr[nr.gid_i.notna()].drop_duplicates("gid_i")
    nr = nr[nr.gid_i.isin(ref)]
    nr["p"] = pos.reindex(nr.gid_i.astype("int64").to_numpy()).to_numpy()
    nr = nr.sort_values("p").reset_index(drop=True)
    j = feat.iloc[nr.p.to_numpy()].reset_index(drop=True)
    R.stage("schema_coverage")

    # ---------------------------------------------------------------- роли
    bad_roles = sorted(set(nr.role) - set(ROLES))
    R.add("role_vocabulary", not bad_roles, bad_roles, list(ROLES), "роль из словаря ТЗ")
    shares = nr.role.value_counts(normalize=True).reindex(list(ROLES), fill_value=0).round(4).to_dict()
    max_share = max(shares.values())
    R.add("role_distribution", max_share <= 0.85 and sum(v > 0 for v in shares.values()) >= 3, shares,
          "max доля ≤0.85, ролей ≥3", "доли ролей; санити-граница, не цель", required=False)
    trunc_term = int(((nr.role == "terminal") & j.truncated.to_numpy()).sum())
    R.add("terminal_not_truncated", trunc_term == 0, trunc_term, 0,
          "terminal у depth=4 без исходящих запрещён: выхода не видно по построению обхода")
    viol = {
        "consolidator_in_deg<2": int(((nr.role == "consolidator") & (j.in_deg.to_numpy() < 2)).sum()),
        "distributor_out_deg<2": int(((nr.role == "distributor") & (j.out_deg.to_numpy() < 2)).sum()),
        "transit_no_in_or_out": int(((nr.role == "transit") & ((j.in_deg.to_numpy() == 0) | (j.out_deg.to_numpy() == 0))).sum()),
        "terminal_no_in": int(((nr.role == "terminal") & (j.in_deg.to_numpy() == 0)).sum()),
        "coordinator_no_in_or_out": int(((nr.role == "coordinator") & ((j.in_deg.to_numpy() == 0) | (j.out_deg.to_numpy() == 0))).sum()),
        "isolated_not_peripheral": int(((j.in_deg.to_numpy() + j.out_deg.to_numpy() == 0) & (nr.role != "peripheral")).sum()),
    }
    R.add("role_structure_consistency", sum(viol.values()) == 0, viol, "все 0",
          "минимальная структура под роль по parquet", required=False)

    rs_bad = int(((nr.role_score_f < 0) | (nr.role_score_f > 1)).sum())
    ps_bad = int(((nr.priority_f < 0) | (nr.priority_f > 1)).sum())
    R.add("role_score_range", rs_bad == 0, {"out_of_range": rs_bad, "min": nr.role_score_f.min(), "max": nr.role_score_f.max()}, "[0;1]")
    R.add("priority_score_range", ps_bad == 0, {"out_of_range": ps_bad, "min": nr.priority_f.min(), "max": nr.priority_f.max()}, "[0;1]",
          "сырой скор идёт в priority_raw (0…41,2 на данных v1, потолок 7·ln 2248 + 1 ≈ 55,0); "
          "priority_score = priority_raw / max(priority_raw)")

    ev = nr.evidence.astype(str)
    ev_bad = {"empty": int((ev.str.strip() == "").sum()), "over_200": int((ev.str.len() > EVIDENCE_MAX).sum()),
              "no_digit": int((~ev.str.contains(DIGIT_RE)).sum()),
              "newline": int((ev.str.contains("\n", regex=False) | ev.str.contains("\r", regex=False)).sum()),
              "mock_prefix": int(ev.str.strip().str.lower().str.startswith("mock").sum())}
    R.add("evidence_format", sum(ev_bad.values()) == 0, {**ev_bad, "max_len": int(ev.str.len().max()) if len(ev) else 0},
          "непусто, ≤200, есть цифра, без перевода строки, без префикса mock (план §3.3)")
    tr = j.truncated.to_numpy()
    mention = ev[tr].str.lower().map(lambda s: any(w in s for w in BOUNDARY_WORDS))
    R.add("evidence_mentions_boundary", bool(mention.all()) if tr.any() else None,
          {"truncated": int(tr.sum()), "mention": int(mention.sum())}, "все depth=4 без выхода",
          "в evidence узла на границе выгрузки есть слово о границе", required=False)
    R.stage("roles_scores_evidence")

    # ---------------------------------------------------------------- top_nodes
    tg_good, tg = parse_gid(tp.gid)
    trank = pd.to_numeric(tp["rank"], errors="coerce")
    tps = pd.to_numeric(tp.priority_score, errors="coerce")
    R.add("top_min_rows", len(tp) >= TOP_MIN, len(tp), f"≥{TOP_MIN}")
    rank_ok = bool((trank.to_numpy() == np.arange(1, len(tp) + 1)).all())
    nonincr = bool((np.diff(tps.to_numpy()) <= 1e-12).all()) and not tps.isna().any()
    R.add("top_rank_sorted", rank_ok and nonincr, {"rank_1..n": rank_ok, "priority_non_increasing": nonincr},
          "rank 1..n, priority по убыванию")
    by_gid = nr.set_index(nr.gid_i.astype("int64"))
    tgi = tg.dropna().astype("int64")
    in_nr = tgi.isin(by_gid.index)
    R.add("top_gid_in_nodes", bool(tg_good.all() and in_nr.all() and not tgi.duplicated().any()),
          {"bad_gid": int((~tg_good).sum()), "not_in_nodes_roles": int((~in_nr).sum()), "dup": int(tgi.duplicated().sum())}, "все 0")
    tj = tp[tg_good.to_numpy()].assign(g=tgi.to_numpy())
    tj = tj[tj.g.isin(by_gid.index)]
    role_mis = int((tj.role.to_numpy() != by_gid.loc[tj.g, "role"].to_numpy()).sum())
    tj_ps = pd.to_numeric(tj.priority_score, errors="coerce").to_numpy()
    ps_mis = int((~(np.abs(tj_ps - by_gid.loc[tj.g, "priority_f"].to_numpy()) <= 1e-6)).sum())
    R.add("top_matches_nodes", role_mis == 0 and ps_mis == 0, {"role_mismatch": role_mis, "priority_mismatch": ps_mis}, "все 0",
          "роль и priority_score в top_nodes совпадают с nodes_roles (нечисловой priority считается расхождением)")
    k = len(tp)
    best = set(nr.sort_values(["priority_f", "gid_i"], ascending=[False, True]).gid_i.astype("int64").head(k))
    R.add("top_is_topk_by_priority", set(tgi) == best, {"overlap": len(set(tgi) & best), "k": k}, "overlap = k",
          "top_nodes — первые k по priority_score из nodes_roles (при равенстве по gid)", required=False)
    why = tp.why.astype(str)
    why_empty = int((why.str.strip() == "").sum())
    R.add("top_why_nonempty", why_empty == 0, why_empty, 0, "why непустой (план §3.3)")
    R.add("top_why_format", bool((why.str.contains(DIGIT_RE) & (why.str.len() <= EVIDENCE_MAX)).all()),
          {"no_digit": int((~why.str.contains(DIGIT_RE)).sum()), "over_200": int((why.str.len() > EVIDENCE_MAX).sum())},
          "есть цифра, ≤200", required=False)
    R.stage("top_checks")

    # ---------------------------------------------------------------- clusters
    c_id_raw = pd.to_numeric(cl.cluster_id, errors="coerce")
    c_id = c_id_raw.where(c_id_raw % 1 == 0)
    c_nn = pd.to_numeric(cl.n_nodes, errors="coerce")
    c_ns = pd.to_numeric(cl.n_seed, errors="coerce")
    c_sk = pd.to_numeric(cl.sum_kzt_internal, errors="coerce")
    cl_bad = {"cluster_id_nan_or_nonint": int(c_id.isna().sum()),
              "n_nodes_nan_or_nonint": int((c_nn.isna() | (c_nn % 1 != 0)).sum()),
              "n_seed_nan_or_nonint": int((c_ns.isna() | (c_ns % 1 != 0)).sum()),
              "sum_kzt_internal_nan": int(c_sk.isna().sum())}
    R.add("schema_clusters_dtypes", sum(cl_bad.values()) == 0, cl_bad, "все 0",
          "cluster_id, n_nodes, n_seed — целые; sum_kzt_internal — число")
    ids_nodes = set(nr.cid.dropna().astype(int))
    ids_cl = set(c_id.dropna().astype(int))
    R.add("cluster_ids_consistent", not c_id.dropna().duplicated().any() and ids_nodes == ids_cl and not nr.cid.isna().any(),
          {"dup_in_clusters": int(c_id.dropna().duplicated().sum()), "only_in_nodes": len(ids_nodes - ids_cl),
           "only_in_clusters": len(ids_cl - ids_nodes), "nodes_without_cluster": int(nr.cid.isna().sum()),
           "n_clusters": len(ids_cl)}, "все 0", "cluster_id у каждого узла и ровно одна строка в clusters.csv")

    lab = np.full(n, -1, dtype=int)
    lab[nr.p.to_numpy()] = nr.cid.fillna(-1).astype(int).to_numpy()
    cnt = pd.Series(lab).value_counts()
    seeds = pd.Series(feat.is_seed.to_numpy()).groupby(lab).sum()
    clx = pd.DataFrame({"cid": c_id.astype("Int64"), "n_nodes": c_nn, "n_seed": c_ns, "kzt": c_sk,
                        "top": cl.top_gids, "hyp": cl.hypothesis}).dropna(subset=["cid"])
    clx["cid"] = clx.cid.astype(int)
    nn_mis = int((clx.n_nodes.to_numpy() != cnt.reindex(clx.cid).fillna(0).to_numpy()).sum())
    R.add("cluster_n_nodes", nn_mis == 0 and c_nn.sum() == n, {"sum": c_nn.sum(), "row_mismatch": nn_mis}, n)
    ns_mis = int((clx.n_seed.to_numpy() != seeds.reindex(clx.cid).fillna(0).to_numpy()).sum())
    R.add("cluster_n_seed", ns_mis == 0 and c_ns.sum() == n_seed_total, {"sum": c_ns.sum(), "row_mismatch": ns_mis}, n_seed_total)
    ls, ld = lab[e.s.to_numpy()], lab[e.d.to_numpy()]
    inside = (ls == ld) & (ls >= 0)
    internal = pd.Series(e.sum_kzt.to_numpy()[inside]).groupby(ls[inside]).sum()
    kzt_mis = int((~(np.abs(clx.kzt.to_numpy() - internal.reindex(clx.cid).fillna(0).to_numpy()) <= KZT_TOL)).sum())
    R.add("cluster_sum_kzt_internal", kzt_mis == 0 and float(c_sk.sum()) <= total_kzt + KZT_TOL and bool((c_sk <= total_kzt + KZT_TOL).all()),
          {"sum": c_sk.sum(), "turnover": total_kzt, "share": c_sk.sum() / total_kzt, "row_mismatch": kzt_mis},
          f"≤{total_kzt:.0f}; строка = пересчёт ±{KZT_TOL} KZT",
          "внутренний оборот = сумма направленных рёбер с обоими концами в кластере")
    top_bad, top_empty = 0, 0
    for cid, top in zip(clx.cid, clx.top):
        items = [x.strip() for x in str(top).replace(";", ",").split(",") if x.strip()]
        if not items:
            top_empty += 1
            continue
        for x in items:
            if not GID_RE.match(x) or int(x) not in pos.index or lab[pos[int(x)]] != cid:
                top_bad += 1
    R.add("cluster_top_gids_subset", top_bad == 0 and top_empty == 0, {"outside_cluster": top_bad, "empty_top": top_empty}, 0,
          "top_gids непуст, каждый gid принадлежит своему кластеру")
    hyp = clx.hyp.astype(str)
    hyp_empty = int((hyp.str.strip() == "").sum())
    R.add("cluster_hypothesis_nonempty", hyp_empty == 0, hyp_empty, 0, "hypothesis непустая (план §3.3)")
    R.add("cluster_hypothesis_format", bool(hyp.str.contains(DIGIT_RE).all()),
          {"no_digit": int((~hyp.str.contains(DIGIT_RE)).sum())}, "есть число", required=False)
    disconnected = 0
    order = np.argsort(lab, kind="stable")
    bounds = np.flatnonzero(np.diff(lab[order])) + 1
    for grp in np.split(order, bounds):
        if len(grp) > 1 and not nx.is_connected(U.subgraph(grp.tolist())):
            disconnected += 1
    R.add("cluster_connected_in_U", disconnected == 0, disconnected, 0,
          "каждый кластер связен в ненаправленной проекции U")
    R.stage("cluster_checks")

    # ---------------------------------------------------------------- детерминизм
    hashes = {k: sha256(p) for k, p in paths.items()}
    if compare is not None:
        other = {k: sha256(compare / f"{k}.csv") if (compare / f"{k}.csv").exists() else None for k in paths}
        same = {k: hashes[k] == other[k] for k in paths}
        R.add("determinism_two_runs", all(same.values()), same, "все True", f"сравнение с {compare}")
    else:
        R.add("determinism_two_runs", None, None, "все True",
              "не запускалось: дайте --compare <каталог второго прогона>", required=False)
    R.stage("determinism")

    # ---------------------------------------------------------------- устойчивость кластеров
    lv = {s: louvain_labels(U, s) for s in (42, 1, 7)}
    lab42a = lv[42]
    full = bool((lab >= 0).all())
    R.add("cluster_matches_reference", None,
          {"ami": ami(lab, lab42a), "ari": ari(lab, lab42a), "identical_ids": bool((lab == lab42a).all())}, 1.0,
          "выгрузка против эталонного Louvain seed 42 на U; 1,0 ожидается, если U строится по возрастанию gid "
          "и в порядке edges.parquet (ds_system_design §3); при другом порядке вставки 0,93–0,96, как между seed",
          required=False)
    pairs = {}
    for a_, b_ in ((42, 1), (42, 7), (1, 7)):
        pairs[f"louvain{a_}~louvain{b_}"] = {"ami": ami(lv[a_], lv[b_]), "ari": ari(lv[a_], lv[b_])}
    sub = {f"csv~louvain{s}": {"ami": ami(lab, lv[s]), "ari": ari(lab, lv[s])} for s in (42, 1, 7)}
    min_ami = min(v["ami"] for v in pairs.values())
    R.add("cluster_stability_seed", min_ami >= 0.9, {"n_communities": {s: int(lv[s].max() + 1) for s in lv}, **pairs, **sub},
          "AMI между seed ≥0.90", "эталонный Louvain на U; строки csv~ — совпадение выгрузки с эталоном", required=False)
    res = {}
    for r_ in (0.8, 1.2):
        lr = louvain_labels(U, 42, r_)
        res[f"res{r_}"] = {"n_communities": int(lr.max() + 1), "ami_vs_res1": ami(lr, lab42a), "ari_vs_res1": ari(lr, lab42a),
                           "ami_vs_csv": ami(lr, lab)}
    R.add("cluster_stability_resolution", min(v["ami_vs_res1"] for v in res.values()) >= 0.85, res,
          "AMI(0.8|1.2 ~ 1.0) ≥0.85", "seed 42; соседние resolution", required=False)
    R.add("cluster_modularity", None,
          {"csv": modularity(U, lab) if full else None, "louvain42": modularity(U, lab42a),
           "n_clusters_csv": len(set(lab.tolist()) - {-1}), "n_clusters_louvain42": int(lab42a.max() + 1)}, None,
          "Q на явной U (вес — KZT в обе стороны), γ = 1,0; эталон 0,8595; csv = null, если не все узлы в кластерах",
          group="c", required=False)
    R.stage("cluster_stability")

    # ---------------------------------------------------------------- эталон через пайплайн, сверка, шум, ablation
    from pipeline.rules import FAST_TRANSIT_WEIGHT, SCORE_TERMS
    ref = pipeline_reference(data_dir)
    assert (ref.gid.to_numpy(np.int64) == gids).all(), "порядок gid эталона пайплайна"
    bc = ref.betweenness.to_numpy(float)
    flag = ref.fast_transit_flag.astype(float).to_numpy()
    terms = {c: ref[f"c_{c}"].to_numpy(float) for c in SCORE_TERMS}
    score = ref.priority_raw.to_numpy(float)
    R.stage("pipeline_reference")

    meta0 = {}
    try:
        if (out_dir / "run_meta.json").exists():
            meta0 = json.loads((out_dir / "run_meta.json").read_text(encoding="utf-8"))
            meta0 = meta0 if isinstance(meta0, dict) else {}
    except Exception:
        meta0 = {}

    # сверка дополнительных колонок CSV с parquet
    ref_cols = {"in_deg": feat.in_deg, "out_deg": feat.out_deg, "in_tx": feat.in_tx, "out_tx": feat.out_tx,
                "depth": feat.depth, "is_seed": feat.is_seed.astype(float),
                "in_kzt": feat.in_kzt, "out_kzt": feat.out_kzt,
                "pass_kzt": pd.Series(np.minimum(feat.in_kzt, feat.out_kzt)),
                # pass_through в CSV пайплайна = pass_ratio глоссария: min/max видимых потоков, 0 без рёбер
                "pass_through": pd.Series(np.where(np.maximum(feat.in_kzt, feat.out_kzt) > 0,
                                                   np.minimum(feat.in_kzt, feat.out_kzt)
                                                   / np.maximum(np.maximum(feat.in_kzt, feat.out_kzt), 1e-12), 0.0)),
                "betweenness": pd.Series(bc), "truncated_by_depth": feat.truncated.astype(float)}
    tol = {"in_kzt": 0.01, "out_kzt": 0.01, "pass_kzt": 0.01, "pass_through": 1e-3, "betweenness": 1e-6}
    fm = {}
    for c, refv in ref_cols.items():
        if c not in nr.columns:
            continue
        v = parse_bool(nr[c]) if c in ("is_seed", "truncated_by_depth") else pd.to_numeric(nr[c], errors="coerce")
        rv = refv.to_numpy(float)[nr.p.to_numpy()]
        bad = ~(np.abs(v.to_numpy(float) - rv) <= tol.get(c, 0.0))
        fm[c] = {"mismatch": int(bad.sum()), "example_gid": str(nr.gid_i[bad].iloc[0]) if bad.any() else None}
    if fm:
        R.add("features_match_parquet", all(x["mismatch"] == 0 for x in fm.values()), fm, "0 расхождений",
              "точно: степени, число переводов, depth, is_seed, truncated_by_depth; ±0,01 KZT: суммы, "
              "pass_kzt = min(in_kzt, out_kzt); ±1e-3: pass_through = min/max; ±1e-6: betweenness", required=False)
    else:
        R.add("features_match_parquet", None, "дополнительных колонок нет", None, "", required=False)
    if "priority_raw" in nr.columns:
        pidx = nr.p.to_numpy()
        vm = {}
        for c, tol_ in (("priority_raw", 1e-3), ("priority_score", 1e-3), ("n_terms_above_p95", 0), ("in_queue", 0)):
            if c not in nr.columns:
                continue
            v = pd.to_numeric(nr[c], errors="coerce").to_numpy(float)
            d = np.abs(v - ref[c].to_numpy(float)[pidx])
            bad = ~(d <= tol_)
            vm[c] = {"rows_off": int(bad.sum()), "max_abs": float(np.nanmax(d)) if len(d) else 0.0,
                     "example_gid": str(nr.gid_i[bad].iloc[0]) if bad.any() else None}
        vm["reference_terms"] = list(SCORE_TERMS) + ["fast_transit_flag"]
        vm["max_priority_raw"] = float(score.max())
        R.add("priority_raw_matches_reference", all(x["rows_off"] == 0 for x in vm.values() if isinstance(x, dict)), vm,
              "|Δ| ≤ 1e-3 по скорам, 0 по n_terms_above_p95 и in_queue",
              "эталон — функции пайплайна (load → features.compute → run._temporal_features → priority.v1) "
              "на parquet; расхождение значит, что CSV устарели относительно кода")
    else:
        R.add("priority_raw_matches_reference", None, "колонки priority_raw нет (v0)", None, "", required=False)

    base_top = set(topk(score, gids, 20).tolist())
    rng = np.random.default_rng(seed)
    overlaps = []
    for _ in range(20):
        sc = reference_with_noise(ref, data_dir, rng).priority_raw.to_numpy(float)
        overlaps.append(len(base_top & set(topk(sc, gids, 20).tolist())) / 20)
    R.add("top20_noise_5pct", float(np.mean(overlaps)) >= 0.8,
          {"mean_overlap": float(np.mean(overlaps)), "min_overlap": float(np.min(overlaps)), "repeats": 20},
          "средняя доля пересечения ≥0.80",
          "priority.v1 пайплайна, шум U(0,95;1,05) на каждый перевод: суммы, pass_kzt и быстрый транзит "
          "пересчитываются; степени и betweenness не меняются", required=False)
    abl = ablation_top20(terms, flag, FAST_TRANSIT_WEIGHT, gids, base_top)
    R.add("top20_ablation", min(abl.values()) >= 0.7, abl, "пересечение ≥0.70 без любого слагаемого",
          "вклады c_<признак> эталона пайплайна; без перенормировки p_j", required=False)
    R.stage("score_noise_ablation")

    # ---------------------------------------------------------------- чувствительность ролей к порогам
    base_roles = roles_v0(feat, V0_THRESHOLDS)
    sens = {}
    feat_of = {"coord_in": "in_deg", "coord_out": "out_deg", "dist_out": "out_deg", "cons_in": "in_deg"}
    for key, col in feat_of.items():
        vals = feat[col].to_numpy(float)
        vals = vals[vals > 0]
        for step in (-1, 1):
            th = dict(V0_THRESHOLDS)
            th[key] = _ladder_shift(vals, V0_THRESHOLDS[key], step)
            sens[f"{key}{'+' if step > 0 else '-'}({th[key]:g})"] = float((roles_v0(feat, th) != base_roles).mean())
    for step, band in ((-1, 0.1), (1, 0.3)):
        th = dict(V0_THRESHOLDS, transit_band=band)
        sens[f"transit_band{'+' if step > 0 else '-'}({band:g})"] = float((roles_v0(feat, th) != base_roles).mean())
    R.add("role_threshold_sensitivity", max(sens.values()) <= 0.10, sens, "max доля смены роли ≤0.10",
          "правила заглушки v0; сдвиг порога на соседнюю ступень квантилей P50…P99,5 среди ненулевых; "
          "для transit — полоса ±0,1", required=False)
    R.stage("role_sensitivity")

    # ---------------------------------------------------------------- перестановочный контроль
    perm, note = None, ""
    if temporal_impl == "pipeline":
        try:
            from pipeline import temporal_check as tc
            rc = tc.run_check(pd.read_parquet(data_dir / "transactions.parquet"), n_perm, seed)
            rows = {r["null"]: r for r in rc["rows"] if r["stat"] == "fast_transit"}
            perm = {"observed": rc["observed"]["fast_transit"], "n_perm": n_perm, "seed": seed,
                    **{k: {"mean": rows[k]["null_mean"], "sd": rows[k]["null_sd"], "p": rows[k]["p"]}
                       for k in ("global", "within_sender")},
                    "pairs_total": rc.get("fast_transit_pairs_total"), "elapsed_s": rc.get("elapsed_s")}
            note = "pipeline.temporal_check.run_check, статистика fast_transit"
        except (Exception, SystemExit) as exc:
            perm = None
            note = f"temporal_check недоступен ({type(exc).__name__}: {str(exc)[:80]}), своя реализация; "
    if perm is None:
        ft = FastTransit(t, n)
        perm = permutation_test(ft, t, n_perm, seed)
        greedy = ft.greedy_pairs()
        perm["greedy_flagged"] = int((greedy >= FT_MIN_PAIRS).sum())
        perm["greedy_pairs_total"] = int(greedy.sum())
        note += "собственная реализация: пары 1-к-1, A≠C, 0,8–1,2, лаг 0–2 дня, ≥2 пар"
    ps_ = []
    for k_ in ("global", "within_sender"):
        try:
            ps_.append(float(perm[k_]["p"]))
        except (KeyError, TypeError, ValueError):
            pass
    if 1 / (n_perm + 1) > 0.01:
        ok_perm = None
        note += "; при N < 99 порог 0,01 недостижим"
    else:
        ok_perm = len(ps_) == 2 and max(ps_) <= 0.01
    R.add("temporal_fast_transit_permutation", ok_perm, perm, "p ≤0.01 при обоих нулях",
          note + "; p = (1 + #нуль ≥ набл.)/(N + 1)", required=False)
    R.stage("permutation")

    # ---------------------------------------------------------------- run_meta.json пайплайна
    meta_p = out_dir / "run_meta.json"
    meta = {}
    if meta_p.exists():
        try:
            meta = json.loads(meta_p.read_text(encoding="utf-8"))
            el = meta.get("elapsed_s")
            R.add("pipeline_runtime", None if el is None else el <= 300,
                  {"elapsed_s": el, "method": meta.get("method"), "stages": meta.get("stages_s", meta.get("stages"))},
                  "≤300 с", "из run_meta.json пайплайна", required=False)
        except Exception as exc:
            meta = {}
            R.add("pipeline_runtime", None, None, "≤300 с", f"run_meta.json не читается: {exc}", required=False)
    else:
        R.add("pipeline_runtime", None, None, "≤300 с", "нет run_meta.json рядом с CSV", required=False)

    # ================================================================ группа (в): ценность
    fq = {}
    for c in SCORE_TERMS:
        v = ref[c].to_numpy(float)
        nz = v[v > 0]
        fq[c] = {"all": {f"p{int(q * 100)}": float(np.quantile(v, q)) for q in (0.5, 0.75, 0.9, 0.95, 0.99)},
                 "nonzero": {f"p{int(q * 100)}": float(np.quantile(nz, q)) for q in (0.5, 0.75, 0.9, 0.95, 0.99)} if len(nz) else None,
                 "n_nonzero": int(len(nz))}
    R.add("feature_quantiles", None, fq, None,
          "семь слагаемых скора по всем 2 248 узлам и среди ненулевых; значения признаков эталона пайплайна "
          "(pass_kzt = 0 у граничных узлов глубины 4 и изолятов)", group="c", required=False)

    rank_prio = nr.assign(pp=nr.p).sort_values(["priority_f", "gid_i"], ascending=[False, True]).pp.to_numpy()
    rank_bc = np.lexsort((gids, -bc))
    rank_kzt = np.lexsort((gids, -(feat.in_kzt.to_numpy() + feat.out_kzt.to_numpy())))
    lcc0, _ = removal_curve(e, n, np.array([], dtype=int), total_kzt)
    table = {"baseline_lcc": lcc0}
    rng = np.random.default_rng(seed)
    rand_orders = [rng.permutation(n) for _ in range(20)]
    for N in (10, 20, 50):
        row = {}
        for nm, rk in (("priority_csv", rank_prio), ("betweenness", rank_bc), ("turnover", rank_kzt)):
            lcc, rem = removal_curve(e, n, rk[:N], total_kzt)
            row[nm] = {"lcc": lcc, "turnover_left": rem}
        rr = [removal_curve(e, n, o[:N], total_kzt) for o in rand_orders]
        row["random_median"] = {"lcc": float(np.median([x[0] for x in rr])), "turnover_left": float(np.median([x[1] for x in rr]))}
        table[f"N={N}"] = row
    r20 = table["N=20"]
    R.add("value_removal_topN", r20["priority_csv"]["turnover_left"] < r20["random_median"]["turnover_left"], table,
          "N=20: остаток оборота по priority_csv < случайного",
          "LCC — крупнейшая слабая компонента, узлов; turnover_left — доля оборота на рёбрах без изъятых узлов; "
          "случайно — медиана 20 повторов", group="c", required=False)

    # очередь проверки: in_queue = 1 ⇔ n_terms_above_p95 ≥ queue_min_terms_above_p95 (pipeline/rules.py)
    if "in_queue" in nr.columns:
        inq = pd.to_numeric(nr.in_queue, errors="coerce").fillna(0).to_numpy(float) >= 1
        n_q = int(inq.sum())
        meta_n = meta.get("n_in_queue") if isinstance(meta, dict) else None
        R.add("queue_count_matches_run_meta", None if meta_n is None else n_q == int(meta_n),
              {"in_queue_csv": n_q, "n_in_queue_run_meta": meta_n}, "равны",
              "число строк in_queue = 1 в nodes_roles.csv против run_meta.json → n_in_queue", required=False)
        if "n_terms_above_p95" in nr.columns:
            nt = pd.to_numeric(nr.n_terms_above_p95, errors="coerce").to_numpy(float)
            kmin = int((meta.get("queue_min_terms_above_p95") if isinstance(meta, dict) else None)
                       or QUEUE_MIN_TERMS_DEFAULT)
            q_bad = int((np.isnan(nt) | ((nt >= kmin) != inq)).sum())
            R.add("queue_rule_consistent", q_bad == 0,
                  {"mismatch": q_bad, "min_terms": kmin, "in_queue_n": n_q,
                   "n_terms_dist": {str(int(k)): int(v) for k, v in
                                    pd.Series(nt[~np.isnan(nt)]).astype(int).value_counts().sort_index().items()}},
                  0, "in_queue = 1 ⇔ n_terms_above_p95 ≥ queue_min_terms_above_p95 из run_meta.json "
                     "(rules.QUEUE_MIN_TERMS_ABOVE_P95); при отсутствии ключа 2", required=False)
        t20 = rank_prio[:20]
        R.add("value_queue_share", None,
              {"in_queue_share": float(inq.mean()), "in_queue_n": n_q, "n_nodes": int(len(inq)),
               "top20_in_queue": int(inq[t20].sum()) if len(inq) == n else None,
               "queue_rule": meta.get("queue_rule") if isinstance(meta, dict) else None},
              None, "доля и число узлов в очереди проверки по колонке in_queue; сколько из топ-20 по priority_score "
                    "в очереди", group="c", required=False)
    else:
        R.add("value_queue_share", None, "колонки in_queue нет (v0)", None, "", group="c", required=False)
    pick = np.random.default_rng(seed).choice(n, 3, replace=False)
    R.add("value_manual_3gid", None, [str(gids[i]) for i in sorted(pick)], "≤60 с на gid",
          "ручной чек по шаблону docs/ds_metrics: роль, правило, числа evidence против карточки", group="c", required=False)
    R.stage("value")
    R.inputs = {**{f"{k}.csv": v for k, v in hashes.items()},
                **{f: sha256(data_dir / f) for f in ("nodes.parquet", "edges.parquet", "transactions.parquet")}}
    return R


# ============================================================ вывод

def _fmt(v, w=64):
    s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
    return s if len(s) <= w else s[: w - 1] + "…"


def print_table(R: Report):
    print(f"{'гр':<2} {'проверка':<36} {'статус':<6} {'значение':<64} порог")
    for c in R.checks:
        st = "INFO" if c["ok"] is None else ("OK" if c["ok"] else ("FAIL" if c["required"] else "WARN"))
        print(f"{c['group']:<2} {c['name']:<36} {st:<6} {_fmt(c['value']):<64} {_fmt(c['threshold'], 40)}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Метрики и проверки выгрузок без разметки")
    ap.add_argument("--data", type=Path, default=Path("task/data"))
    ap.add_argument("--out", type=Path, default=Path("outputs"), help="каталог с тремя CSV")
    ap.add_argument("--report", type=Path, required=True, help="путь metrics.json")
    ap.add_argument("--perm", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--compare", type=Path, default=None, help="каталог CSV второго прогона для проверки детерминизма")
    ap.add_argument("--temporal-impl", choices=["pipeline", "own"], default="pipeline",
                    help="pipeline — pipeline.temporal_check.run_check (по умолчанию); own — своя реализация")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    R = Report()
    try:
        R = run(a.data, a.out, a.perm, a.seed, a.compare, a.temporal_impl, R)
    except Exception as exc:
        R.add("metrics_crash", False, f"{type(exc).__name__}: {exc}"[:300], None,
              "модуль упал, остальные проверки не выполнены")
    t_b = time.perf_counter()
    try:
        from pipeline.baselines import run_baselines
        baselines = run_baselines(a.data, a.out, seed=a.seed)
        b_note = "pipeline.baselines.run_baselines"
    except (Exception, SystemExit) as exc:
        baselines = {"note": f"baselines не посчитаны: {type(exc).__name__}: {str(exc)[:200]}"}
        b_note = baselines["note"]
    R.add("baselines_run", None if "note" in baselines else True,
          {"n_summary": len(baselines.get("summary") or []), "warnings": len(baselines.get("warnings") or [])},
          None, b_note + "; полный результат — ключ baselines отчёта", required=False, group="c")
    R.timing["baselines"] = round(time.perf_counter() - t_b, 3)
    total = round(time.perf_counter() - t0, 3)
    failed = [c["name"] for c in R.checks if c["required"] and c["ok"] is False]
    warned = [c["name"] for c in R.checks if not c["required"] and c["ok"] is False]
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "params": {"data": str(a.data), "out": str(a.out), "perm": a.perm, "seed": a.seed,
                   "compare": None if a.compare is None else str(a.compare), "temporal_impl": a.temporal_impl},
        "versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__, "networkx": nx.__version__},
        "inputs": R.inputs,
        "summary": {"n_checks": len(R.checks), "required_failed": failed, "soft_failed": warned, "elapsed_s": total},
        "timing_s": R.timing,
        "checks": R.checks,
        "baselines": _jsonable(baselines),
    }
    a.report.parent.mkdir(parents=True, exist_ok=True)
    a.report.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print_table(R)
    print(f"\nпроверок {len(R.checks)}; обязательных провалено {len(failed)}; предупреждений {len(warned)}; {total} с")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
