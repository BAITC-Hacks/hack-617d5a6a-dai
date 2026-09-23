"""Сравнение выгрузок «Граф денег» с dummy-моделями на измеримых прокси-исходах.

Меток ролей и «правильного» приоритета в данных нет, поэтому accuracy здесь не считается.
Выгрузка пайплайна (nodes_roles.csv, clusters.csv, top_nodes.csv схемы ТЗ) сравнивается с
простыми заменителями там, где замена архитектурно возможна:

  priority  priority_score против случайного порядка, оборота, числа контрагентов, PageRank
            стартового кода и «seed первыми»; исходы изъятия топ-N (N = 10, 20, 50);
  roles     роли против «все peripheral» и «роль по одному признаку степени»;
  clusters  кластеры против слабосвязных компонент и случайного разбиения тех же размеров;
  temporal  флаг быстрого транзита против случайных дат (200 перестановок, два нуля).

«Лучше dummy» не значит «правильно»: прокси-исходы показывают, что очередь полезнее простого
правила и что роли и кластеры не вырождены, но не подтверждают истинность ролей.

Запуск из корня репозитория:

    python -m pipeline.baselines --data task/data --out <каталог с CSV> --report <json> \
        [--seed 42] [--n-random 20] [--role-fn пакет.модуль:функция]

Из кода: run_baselines(data_dir, out_dir, seed=42, n_random=20, role_fn=None) -> dict.
Модуль не импортирует backend и ничего не пишет, кроме файла --report.
Документация: раздел «Сравнение с dummy-моделями» в docs/ds_metrics_2026-09-23.md.
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.csgraph import breadth_first_order, connected_components
from scipy.special import gammaln

ROLES = ("consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral")
TOP_N = (10, 20, 50)
N_PERM_DATES = 200
NOISE_PCT = 0.05
EPS = 1e-9

# быстрый транзит: то же определение, что в pipeline/metrics.py (docs/ds_metrics_2026-09-23.md)
FT_LAG = (0, 2)          # дней, день выхода − день входа
FT_RATIO = (0.8, 1.2)    # сумма выхода / сумма входа
FT_MIN_PAIRS = 2

BOUNDARY_WORDS = ("depth=4", "depth 4", "глубин", "границ", "колен", "обрыв", "выгрузк")
GID_RE = re.compile(r"^\s*(-?\d{1,19})(?:\.0+)?\s*$")
GIDLIKE_RE = re.compile(r"\d{15,}")
DIGIT_RE = re.compile(r"\d")
FT_PHRASE_RE = re.compile(r"быстр\w*\s+транзит\w*", re.IGNORECASE)
NEG_RE = re.compile(r"(нет|без|не\s)", re.IGNORECASE)
INT_RE = re.compile(r"\d+")
TRUE_WORDS = {"1", "true", "t", "yes", "y", "да"}

# role_fn(nodes[gid, depth, is_seed], edges[src, dst, sum_kzt, n_tx, depth], tx[src, dst, date, sum_kzt])
#   -> pd.Series ролей с индексом gid (int64) или массив в порядке nodes, отсортированных по gid
RoleFn = Callable[[pd.DataFrame, pd.DataFrame, pd.DataFrame], "pd.Series | np.ndarray"]


# ============================================================ данные

@dataclass
class Data:
    nodes: pd.DataFrame      # parquet, отсортирован по gid
    edges: pd.DataFrame      # parquet как есть
    tx: pd.DataFrame         # parquet как есть
    gids: np.ndarray         # int64, порядок = индексы 0..n-1
    n: int
    depth: np.ndarray
    is_seed: np.ndarray
    s: np.ndarray            # рёбра пар: индексы узлов
    d: np.ndarray
    w: np.ndarray            # sum_kzt пары
    total: float
    in_deg: np.ndarray
    out_deg: np.ndarray
    in_kzt: np.ndarray
    out_kzt: np.ndarray
    ts: np.ndarray           # переводы: индексы узлов
    td: np.ndarray
    tamt: np.ndarray
    tday: np.ndarray         # номер дня (дни от 1970-01-01)
    dropped_edges: int
    dropped_tx: int


def _positions(pos: pd.Series, values) -> np.ndarray:
    return pos.reindex(np.asarray(values, dtype=np.int64)).to_numpy(dtype=float)


def load_data(data_dir: Path) -> Data:
    nodes = pd.read_parquet(data_dir / "nodes.parquet").sort_values("gid").reset_index(drop=True)
    edges = pd.read_parquet(data_dir / "edges.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    gids = nodes.gid.to_numpy(np.int64)
    n = len(gids)
    pos = pd.Series(np.arange(n), index=gids)

    e = edges.groupby(["src", "dst"], as_index=False).agg(sum_kzt=("sum_kzt", "sum"))
    s, d = _positions(pos, e.src), _positions(pos, e.dst)
    ok = ~(np.isnan(s) | np.isnan(d))
    s, d, w = s[ok].astype(int), d[ok].astype(int), e.sum_kzt.to_numpy(float)[ok]

    ts, td = _positions(pos, tx.src), _positions(pos, tx.dst)
    tok = ~(np.isnan(ts) | np.isnan(td))
    days = pd.to_datetime(tx.date).to_numpy("datetime64[D]").astype(np.int64)

    return Data(
        nodes=nodes, edges=edges, tx=tx, gids=gids, n=n,
        depth=nodes.depth.to_numpy(int), is_seed=nodes.is_seed.to_numpy(bool),
        s=s, d=d, w=w, total=float(w.sum()),
        in_deg=np.bincount(d, minlength=n), out_deg=np.bincount(s, minlength=n),
        in_kzt=np.bincount(d, weights=w, minlength=n), out_kzt=np.bincount(s, weights=w, minlength=n),
        ts=ts[tok].astype(int), td=td[tok].astype(int), tamt=tx.sum_kzt.to_numpy(float)[tok],
        tday=days[tok], dropped_edges=int((~ok).sum()), dropped_tx=int((~tok).sum()),
    )


# ============================================================ чтение CSV схемы ТЗ

def _parse_gid(col: pd.Series) -> pd.Series:
    return col.astype(str).str.extract(GID_RE, expand=False)


def _truthy(v: str) -> bool:
    v = str(v).strip().lower()
    if v in TRUE_WORDS:
        return True
    try:
        return float(v) > 0
    except ValueError:
        return False


def read_nodes_roles(path: Path, D: Data) -> tuple[pd.DataFrame, dict]:
    """Выравнивает nodes_roles.csv по nodes.parquet. Пропуски не роняют расчёт, а считаются."""
    raw = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in ("gid", "role", "role_score", "cluster_id", "priority_score", "evidence"):
        if c not in raw.columns:
            raw[c] = ""
    g = _parse_gid(raw.gid)
    bad_gid = int(g.isna().sum())
    raw = raw[g.notna()].copy()
    raw["gid"] = g[g.notna()].astype(np.int64)
    dup = int(raw.gid.duplicated().sum())
    raw = raw.drop_duplicates("gid").set_index("gid")
    foreign = int((~raw.index.isin(D.gids)).sum())
    df = raw.reindex(D.gids)
    missing = int(df.role.isna().sum())

    out = pd.DataFrame(index=D.gids)
    out["role"] = df.role.fillna("").astype(str).str.strip().to_numpy()
    out["priority"] = pd.to_numeric(df.priority_score, errors="coerce").to_numpy(float)
    raw_cid = df.cluster_id.fillna("").astype(str).str.strip()
    num_cid = pd.to_numeric(raw_cid, errors="coerce")
    no_cluster = int((raw_cid == "").sum())
    out["cluster"] = [f"_none_{i}" if r == "" else (repr(float(v)) if not math.isnan(v) else r)
                      for i, (r, v) in enumerate(zip(raw_cid.to_numpy(), num_cid.to_numpy(float)))]
    out["evidence"] = df.evidence.fillna("").astype(str).to_numpy()

    flags_tok = (df["flags"].fillna("").astype(str).str.contains(r"\bfast_transit", regex=True)
                 if "flags" in df.columns else pd.Series(False, index=df.index))
    if "fast_transit_flag" in df.columns:
        out["ft_flag"] = df.fast_transit_flag.fillna("").map(_truthy).to_numpy(bool)
        ft_source = "колонка fast_transit_flag"
    elif flags_tok.any():
        out["ft_flag"] = flags_tok.to_numpy(bool)
        ft_source = "метка fast_transit в колонке flags"
    else:
        hits = out.evidence.map(_evidence_fast_transit)
        if hits.any():
            out["ft_flag"] = hits.to_numpy(bool)
            ft_source = "фраза «быстрый транзит» в evidence"
        else:
            ft_source = None
    info = {
        "rows_csv": int(len(raw) + dup + bad_gid), "gid_unparsed": bad_gid, "gid_duplicates": dup,
        "gid_foreign": foreign, "gid_missing": missing, "cluster_id_missing": no_cluster,
        "priority_nan": int(np.isnan(out.priority.to_numpy()).sum()),
        "priority_unique": int(pd.Series(out.priority).nunique()),
        "fast_transit_source": ft_source,
    }
    return out, info


def _evidence_fast_transit(text: str) -> bool:
    """«быстрый транзит: 3 пар» — да; «нет быстрого транзита», «быстрый транзит: 0 пар» — нет."""
    for m in FT_PHRASE_RE.finditer(text):
        before = text[max(0, m.start() - 6):m.start()]
        after = text[m.end():m.end() + 16]
        if NEG_RE.search(before) or re.match(r"\W*нет", after, re.IGNORECASE):
            continue
        num = INT_RE.search(after)
        if num is not None and int(num.group()) < FT_MIN_PAIRS:
            continue
        return True
    return False


def read_top(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        return None
    t = pd.read_csv(path, dtype=str, keep_default_na=False)
    for c in ("rank", "gid", "why"):
        if c not in t.columns:
            t[c] = ""
    t["rank_num"] = pd.to_numeric(t["rank"], errors="coerce")
    return t.sort_values("rank_num", na_position="last").reset_index(drop=True)


# ============================================================ общее

def _numeric_text(text: str) -> bool:
    """Есть число, кроме самого gid (последовательности из ≥15 цифр не считаются)."""
    return bool(DIGIT_RE.search(GIDLIKE_RE.sub(" ", text)))


def _band(values) -> dict:
    a = np.asarray(values, dtype=float)
    return {"median": float(np.median(a)), "p5": float(np.percentile(a, 5)), "p95": float(np.percentile(a, 95))}


def _verdict(ours: float, ref, direction: int) -> str:
    if direction == 0 or ours is None or ref is None:
        return "справочно"
    if isinstance(ref, dict):
        lo, hi = ref["p5"], ref["p95"]
        if abs(ours - lo) <= EPS and abs(ours - hi) <= EPS:
            return "равно"
        if ours > hi + EPS:
            return "лучше" if direction > 0 else "хуже"
        if ours < lo - EPS:
            return "хуже" if direction > 0 else "лучше"
        return "в полосе случайного"
    diff = float(ours) - float(ref)
    if abs(diff) <= EPS:
        return "равно"
    return "лучше" if diff * direction > 0 else "хуже"


def _aggregate(by_n: dict) -> str:
    vals = list(by_n.values())
    if len(set(vals)) == 1:
        return vals[0]
    return "смешанно (" + ", ".join(f"N={k}: {v}" for k, v in by_n.items()) + ")"


def _summary_line(head: str, verdicts: dict, labels: dict) -> str:
    order = ("лучше", "хуже", "равно", "в полосе случайного")
    groups: dict[str, list[str]] = {k: [] for k in order}
    mixed = []
    for key, v in verdicts.items():
        if v == "справочно":
            continue
        if v in groups:
            groups[v].append(labels[key])
        else:
            mixed.append(f"{labels[key]} {v[len('смешанно '):]}")
    parts = [f"{k} по {', '.join(groups[k])}" for k in order if groups[k]]
    if mixed:
        parts.append("смешанно по " + "; ".join(mixed))
    return f"{head}: " + ("; ".join(parts) if parts else "нет сравнимых исходов")


def _order_by_score(score: np.ndarray, gids: np.ndarray) -> np.ndarray:
    sc = np.where(np.isfinite(score), score, -np.inf)
    return np.lexsort((gids, -sc))


def _codes(labels) -> np.ndarray:
    return np.unique(np.asarray(labels).astype(str), return_inverse=True)[1]


def _jsonable(x):
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, (float, np.floating)):
        v = float(x)
        return None if math.isnan(v) or math.isinf(v) else round(v, 6)
    return x


# ============================================================ 1. приоритет

# (ключ, направление: +1 больше лучше, −1 меньше лучше, 0 справочно, подпись, подпись для «лучше по …»)
PRIO_METRICS = (
    ("removed_turnover_share", +1, "снятый оборот", "снятому обороту"),
    ("lcc_after", -1, "LCC после изъятия", "LCC после изъятия"),
    ("seed_branches_hit", +1, "затронутые seed-ветви", "затронутым seed-ветвям"),
    ("depth4_share", -1, "доля depth 4", "доле depth 4"),
    ("evidence_nonempty_share", +1, "evidence непустой", "непустому evidence"),
    ("evidence_numeric_share", +1, "evidence с числом", "evidence с числом"),
)
PRIO_METHODS = {
    "ours": "priority_score из nodes_roles.csv, по убыванию; при равенстве gid по возрастанию",
    "random": "случайный порядок узлов",
    "turnover": "in_kzt + out_kzt по убыванию",
    "degree": "in_deg + out_deg по убыванию",
    "pagerank": "PageRank стартового кода (граф из edges, weight=sum_kzt, alpha 0,85)",
    "seed_first": "все seed первыми в случайном порядке, затем остальные в случайном порядке",
}


def pagerank_starter(D: Data) -> np.ndarray:
    G = nx.DiGraph()
    G.add_weighted_edges_from(zip(D.s.tolist(), D.d.tolist(), D.w.tolist()), weight="sum_kzt")
    pr = nx.pagerank(G, weight="sum_kzt") if G.number_of_edges() else {}
    out = np.zeros(D.n)
    for k, v in pr.items():
        out[k] = v
    return out


def seed_reach(D: Data) -> np.ndarray:
    """reach[k, v] = узел v достижим из k-го seed по исходящим рёбрам (сам seed входит)."""
    A = sparse.csr_matrix((np.ones(len(D.s)), (D.s, D.d)), shape=(D.n, D.n))
    seeds = np.flatnonzero(D.is_seed)
    reach = np.zeros((len(seeds), D.n), dtype=bool)
    for k, i in enumerate(seeds):
        reach[k, breadth_first_order(A, int(i), directed=True, return_predecessors=False)] = True
    return reach


def removal_outcomes(D: Data, reach: np.ndarray, removed: np.ndarray,
                     ev_nonempty: np.ndarray, ev_numeric: np.ndarray) -> dict:
    alive = np.ones(D.n, dtype=bool)
    alive[removed] = False
    keep = alive[D.s] & alive[D.d]
    A = sparse.coo_matrix((np.ones(int(keep.sum())), (D.s[keep], D.d[keep])), shape=(D.n, D.n))
    _, lab = connected_components(A, directed=True, connection="weak")
    lab = lab[alive]
    share = (lambda x: float(x.mean())) if len(removed) else (lambda x: float("nan"))
    return {
        "removed_turnover_share": float(D.w[~keep].sum() / D.total) if D.total else float("nan"),
        "lcc_after": int(np.bincount(lab).max()) if len(lab) else 0,
        "seed_branches_hit": int(reach[:, removed].any(axis=1).sum()) if len(removed) else 0,
        "depth4_share": share(D.depth[removed] == 4),
        "evidence_nonempty_share": share(ev_nonempty[removed]),
        "evidence_numeric_share": share(ev_numeric[removed]),
    }


def priority_block(D: Data, nr: pd.DataFrame, top: pd.DataFrame | None, seed: int, n_random: int) -> dict:
    rng = np.random.default_rng(seed)
    ev = nr.evidence.to_numpy(object)
    ev_nonempty = np.array([bool(str(x).strip()) for x in ev])
    ev_numeric = np.array([_numeric_text(str(x)) for x in ev])
    reach = seed_reach(D)
    Ns = [N for N in TOP_N if N <= D.n] or [D.n]

    det_orders = {
        "ours": _order_by_score(nr.priority.to_numpy(float), D.gids),
        "turnover": _order_by_score(D.in_kzt + D.out_kzt, D.gids),
        "degree": _order_by_score((D.in_deg + D.out_deg).astype(float), D.gids),
        "pagerank": _order_by_score(pagerank_starter(D), D.gids),
    }
    seeds, rest = np.flatnonzero(D.is_seed), np.flatnonzero(~D.is_seed)
    rand_orders = {
        "random": [rng.permutation(D.n) for _ in range(n_random)],
        "seed_first": [np.concatenate([rng.permutation(seeds), rng.permutation(rest)]) for _ in range(n_random)],
    }

    outcomes: dict = {}
    for name, order in det_orders.items():
        outcomes[name] = {N: removal_outcomes(D, reach, order[:N], ev_nonempty, ev_numeric) for N in Ns}
    for name, orders in rand_orders.items():
        outcomes[name] = {}
        for N in Ns:
            runs = [removal_outcomes(D, reach, o[:N], ev_nonempty, ev_numeric) for o in orders]
            outcomes[name][N] = {k: _band([r[k] for r in runs]) for k, _, _, _ in PRIO_METRICS}

    # справочно для нашего скора: why из top_nodes.csv по первым N строкам
    if top is not None:
        for N in Ns:
            why = top.why.head(N).astype(str)
            outcomes["ours"][N]["top_csv_rows_used"] = int(len(why))
            outcomes["ours"][N]["why_numeric_share"] = float(why.map(_numeric_text).mean()) if len(why) else None

    labels = {k: dat for k, _, _, dat in PRIO_METRICS}
    verdicts, summary = {}, []
    for dummy in ("random", "turnover", "degree", "pagerank", "seed_first"):
        verdicts[dummy] = {}
        for key, direction, _, _ in PRIO_METRICS:
            by_n = {N: _verdict(outcomes["ours"][N][key], outcomes[dummy][N][key], direction) for N in Ns}
            verdicts[dummy][key] = {"by_N": by_n, "overall": _aggregate(by_n)}
        summary.append(_summary_line(
            f"priority (изъятие топ-N, N={'/'.join(map(str, Ns))}, seed {seed}"
            + (f", {n_random} повторов" if dummy in rand_orders else "") + f"): наш скор против {dummy}",
            {k: v["overall"] for k, v in verdicts[dummy].items()}, labels))

    lcc0 = removal_outcomes(D, reach, np.array([], dtype=int), ev_nonempty, ev_numeric)["lcc_after"]
    return {
        "conditions": {
            "N": Ns, "seed": seed, "n_random": n_random, "turnover_total_kzt": round(D.total, 2),
            "lcc_before": lcc0, "n_seed": int(D.is_seed.sum()), "n_nodes": D.n,
            "random_band": "медиана и перцентили 5–95 % по n_random повторам; «лучше» и «хуже» только вне полосы",
            "removed_turnover_share": "Σ sum_kzt рёбер, инцидентных изъятым узлам / общий оборот",
            "lcc_after": "узлов в крупнейшей слабосвязной компоненте оставшегося графа (изоляты считаются)",
            "seed_branches_hit": "seed, у которых изъятый узел достижим по исходящим рёбрам (сам seed входит)",
            "evidence": "для всех методов evidence берётся из nodes_roles.csv у выбранных узлов; "
                        "«с числом» = есть цифра вне gid (≥15 цифр подряд не считаются)",
        },
        "methods": PRIO_METHODS,
        "metrics": {k: {"label": lab, "direction": "больше лучше" if dr > 0 else "меньше лучше"}
                    for k, dr, lab, _ in PRIO_METRICS},
        "outcomes": outcomes,
        "verdicts": verdicts,
        "_summary": summary,
    }


# ============================================================ 2. роли

ROLE_METRICS = (
    ("depth4_terminal", -1, "terminal на depth 4", "числу terminal на depth 4"),
    ("noise_role_change_share", -1, "смена роли при шуме ±5 %", "смене роли при шуме ±5 %"),
    ("share_non_peripheral", 0, "доля не peripheral", "доле не peripheral"),
    ("entropy_bits", 0, "энтропия ролей, бит", "энтропии ролей"),
    ("agreement_with_single_feature", 0, "совпадение с dummy по одному признаку", "совпадению с dummy"),
    ("kappa_with_single_feature", 0, "каппа Коэна с dummy по одному признаку", "каппе Коэна"),
)


def dummy_single_feature(in_deg: np.ndarray, out_deg: np.ndarray) -> np.ndarray:
    """terminal если out_deg = 0; distributor если out_deg ≥ 10; consolidator если in_deg ≥ 3;
    иначе peripheral. Проверка сверху вниз, depth не учитывается."""
    r = np.full(len(in_deg), "peripheral", dtype=object)
    r[in_deg >= 3] = "consolidator"
    r[out_deg >= 10] = "distributor"
    r[out_deg == 0] = "terminal"
    return r


def pipeline_v0_roles(nodes: pd.DataFrame, edges: pd.DataFrame, tx: pd.DataFrame) -> pd.Series:
    """role_fn для --role-fn pipeline.baselines:pipeline_v0_roles: правила pipeline/roles_v0.py
    на лёгких признаках (степени, суммы, depth). Импорт ленивый: модуль не зависит от pipeline v0,
    пока адаптер не вызван. Совпадение с CSV на чистых данных отчитывается как role_fn_matches_csv."""
    from pipeline import roles_v0  # noqa: PLC0415

    g = nodes.gid.to_numpy(np.int64)
    by_dst, by_src = edges.groupby("dst"), edges.groupby("src")
    f = nodes[["gid", "depth", "is_seed"]].copy()
    f["in_deg"] = by_dst.src.nunique().reindex(g).fillna(0).astype(int).to_numpy()
    f["out_deg"] = by_src.dst.nunique().reindex(g).fillna(0).astype(int).to_numpy()
    f["in_kzt"] = by_dst.sum_kzt.sum().reindex(g).fillna(0.0).to_numpy(float)
    f["out_kzt"] = by_src.sum_kzt.sum().reindex(g).fillna(0.0).to_numpy(float)
    return pd.Series(roles_v0.apply(f).role.to_numpy(), index=g)


def _single_feature_fn(nodes: pd.DataFrame, edges: pd.DataFrame, tx: pd.DataFrame) -> pd.Series:
    g = nodes.gid.to_numpy(np.int64)
    ind = edges.groupby("dst").src.nunique().reindex(g).fillna(0).to_numpy()
    outd = edges.groupby("src").dst.nunique().reindex(g).fillna(0).to_numpy()
    return pd.Series(dummy_single_feature(ind, outd), index=g)


def _entropy_bits(labels: np.ndarray) -> float:
    _, c = np.unique(labels.astype(str), return_counts=True)
    p = c / c.sum()
    return float(-(p * np.log2(p)).sum()) + 0.0


def _kappa(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a.astype(str), b.astype(str)
    cats = np.union1d(a, b)
    po = float((a == b).mean())
    pe = float(sum((a == c).mean() * (b == c).mean() for c in cats))
    return 1.0 if abs(1 - pe) <= EPS else (po - pe) / (1 - pe)


def _call_role_fn(fn: RoleFn, D: Data, edges: pd.DataFrame, tx: pd.DataFrame) -> np.ndarray:
    nodes = D.nodes[["gid", "depth", "is_seed"]].copy()
    out = fn(nodes, edges.copy(), tx.copy())
    if isinstance(out, pd.DataFrame):
        out = out.set_index("gid")["role"] if "gid" in out.columns else out["role"]
    if isinstance(out, pd.Series) and len(out.index) and out.index.isin(D.gids).mean() > 0.5:
        out = out.reindex(D.gids)  # индекс — gid; иначе порядок строк = nodes, отсортированные по gid
    arr = np.asarray(out, dtype=object)
    if len(arr) != D.n:
        raise ValueError(f"role_fn вернула {len(arr)} ролей, ожидалось {D.n}")
    return np.array(["" if v is None or (isinstance(v, float) and math.isnan(v)) else str(v) for v in arr],
                    dtype=object)


def _noisy_frames(D: Data, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Шум U(1−5 %; 1+5 %) на каждый перевод; суммы пар масштабируются тем же множителем."""
    u = rng.uniform(1 - NOISE_PCT, 1 + NOISE_PCT, len(D.tx))
    tx = D.tx.copy()
    tx["sum_kzt"] = D.tx.sum_kzt.to_numpy(float) * u
    f = (tx.groupby(["src", "dst"]).sum_kzt.sum() / D.tx.groupby(["src", "dst"]).sum_kzt.sum()).rename("f")
    e = D.edges.merge(f.reset_index(), on=["src", "dst"], how="left")
    e["sum_kzt"] = e.sum_kzt * e.f.fillna(1.0)
    return e.drop(columns="f"), tx


def noise_stability(fn: RoleFn, D: Data, seed: int, repeats: int) -> dict:
    rng = np.random.default_rng(seed)
    base = _call_role_fn(fn, D, D.edges, D.tx)
    shares = []
    for _ in range(repeats):
        e, t = _noisy_frames(D, rng)
        shares.append(float((_call_role_fn(fn, D, e, t) != base).mean()))
    return {"mean": float(np.mean(shares)), "max": float(np.max(shares)), "repeats": repeats,
            "_base": base}


def roles_block(D: Data, nr: pd.DataFrame, seed: int, n_random: int, role_fn: RoleFn | None) -> dict:
    single = dummy_single_feature(D.in_deg, D.out_deg)
    methods = {
        "ours": nr.role.to_numpy(object),
        "all_peripheral": np.full(D.n, "peripheral", dtype=object),
        "single_feature": single,
    }
    boundary = np.array([any(w in str(x).lower() for w in BOUNDARY_WORDS) for x in nr.evidence])
    res: dict = {}
    for name, r in methods.items():
        r = r.astype(str)
        d4t = (D.depth == 4) & (r == "terminal")
        vals, cnt = np.unique(r, return_counts=True)
        res[name] = {
            "depth4_terminal": int(d4t.sum()),
            "share_non_peripheral": float((np.isin(r, ROLES) & (r != "peripheral")).mean()),
            "entropy_bits": _entropy_bits(r),
            "entropy_norm": _entropy_bits(r) / math.log2(len(ROLES)),
            "agreement_with_single_feature": float((r == single.astype(str)).mean()),
            "kappa_with_single_feature": _kappa(r, single),
            "distribution": {str(v): int(c) for v, c in zip(vals, cnt)},
            "outside_vocabulary": int((~np.isin(r, ROLES)).sum()),
        }
        if name == "ours":
            res[name]["depth4_terminal_explained"] = int((d4t & boundary).sum())

    # устойчивость к шуму: dummy пересчитываются всегда, наши роли — только через role_fn
    res["all_peripheral"]["noise_role_change_share"] = 0.0
    ns = noise_stability(_single_feature_fn, D, seed, n_random)
    res["single_feature"]["noise_role_change_share"] = ns["mean"]
    if role_fn is None:
        res["ours"]["noise_role_change_share"] = None
        res["ours"]["noise_note"] = ("требует пересчёта пайплайна: передайте role_fn "
                                     "(--role-fn pipeline.baselines:pipeline_v0_roles или свой модуль:функция)")
    else:
        ns = noise_stability(role_fn, D, seed, n_random)
        res["ours"]["noise_role_change_share"] = ns["mean"]
        res["ours"]["noise_role_change_max"] = ns["max"]
        res["ours"]["role_fn_matches_csv"] = float((ns["_base"] == methods["ours"].astype(str)).mean())

    labels = {k: dat for k, _, _, dat in ROLE_METRICS}
    names = {k: lab for k, _, lab, _ in ROLE_METRICS}
    verdicts, summary = {}, []
    for dummy in ("all_peripheral", "single_feature"):
        verdicts[dummy] = {k: _verdict(res["ours"].get(k), res[dummy].get(k), dr) for k, dr, _, _ in ROLE_METRICS}
        line = _summary_line(f"roles (seed {seed}, шум {n_random} повторов): наши роли против {dummy}",
                             verdicts[dummy], labels)
        info = ", ".join(f"{names[k]} {_fmt(res['ours'][k])} против {_fmt(res[dummy][k])}"
                         for k in ("share_non_peripheral", "entropy_bits", "agreement_with_single_feature"))
        extra = "; шум для наших ролей не считался (требует пересчёта пайплайна)" if role_fn is None else ""
        summary.append(f"{line}; справочно: {info}{extra}")
    return {
        "conditions": {
            "seed": seed, "noise_repeats": n_random, "noise": "U(0,95; 1,05) на каждый перевод",
            "single_feature": dummy_single_feature.__doc__.replace("\n", " ").replace("    ", " ").strip(),
            "depth4_terminal": "узлы depth=4 с ролью terminal; у них нет наблюдаемых исходящих по построению выгрузки",
            "entropy": "Шеннон по долям ролей, бит; максимум log2(6) = 2,585",
            "share_non_peripheral": "доля узлов с ролью из словаря ТЗ, кроме peripheral",
            "noise_dummy": "dummy «все peripheral» и dummy по степени не зависят от сумм: их смена роли 0 по построению",
        },
        "methods": res,
        "verdicts": verdicts,
        "_summary": summary,
    }


# ============================================================ 3. кластеры

CLUSTER_METRICS = (
    ("modularity_U", +1, "модулярность на U", "модулярности на U"),
    ("internal_turnover_share", +1, "доля внутреннего оборота", "доле внутреннего оборота"),
    ("n_clusters_ge2_seed", 0, "кластеров с ≥2 seed", "числу кластеров с ≥2 seed"),
    ("n_clusters", 0, "число кластеров", "числу кластеров"),
    ("largest_cluster", 0, "крупнейший кластер, узлов", "крупнейшему кластеру"),
    ("ami_vs_wcc", 0, "AMI с компонентами", "AMI с компонентами"),
)


def undirected_projection(D: Data) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    a, b = np.minimum(D.s, D.d), np.maximum(D.s, D.d)
    u = pd.DataFrame({"a": a, "b": b, "w": D.w}).groupby(["a", "b"], as_index=False).w.sum()
    return u.a.to_numpy(), u.b.to_numpy(), u.w.to_numpy(float)


def modularity(codes: np.ndarray, ua, ub, uw, n: int) -> float:
    """Q = Σ_c [W_c / m − (S_c / 2m)²], как networkx.community.modularity при resolution 1."""
    m = uw.sum()
    if m <= 0:
        return float("nan")
    strength = np.bincount(ua, weights=uw, minlength=n) + np.bincount(ub, weights=uw, minlength=n)
    k = int(codes.max()) + 1
    same = codes[ua] == codes[ub]
    W = np.bincount(codes[ua][same], weights=uw[same], minlength=k)
    S = np.bincount(codes, weights=strength, minlength=k)
    return float((W / m - (S / (2 * m)) ** 2).sum())


def _contingency(a: np.ndarray, b: np.ndarray):
    m = sparse.coo_matrix((np.ones(len(a)), (a, b))).tocsr()
    m.sum_duplicates()
    return m.tocoo()


def _emi(av: np.ndarray, bv: np.ndarray, n: int) -> float:
    """Ожидаемая взаимная информация при случайной перестановке (Vinh и др., 2010)."""
    cache: dict[tuple[int, int], float] = {}
    lg_n = gammaln(n + 1)
    total = 0.0
    for a in av:
        for b in bv:
            key = (int(min(a, b)), int(max(a, b)))
            if key not in cache:
                lo, hi = max(1, a + b - n), min(a, b)
                if lo > hi:
                    cache[key] = 0.0
                else:
                    nij = np.arange(lo, hi + 1, dtype=float)
                    t1 = nij / n * (np.log(nij * n) - np.log(float(a) * float(b)))
                    lg = (gammaln(a + 1) + gammaln(b + 1) + gammaln(n - a + 1) + gammaln(n - b + 1)
                          - lg_n - gammaln(nij + 1) - gammaln(a - nij + 1) - gammaln(b - nij + 1)
                          - gammaln(n - a - b + nij + 1))
                    cache[key] = float((t1 * np.exp(lg)).sum())
            total += cache[key]
    return total


def ami(a: np.ndarray, b: np.ndarray) -> float:
    """Adjusted mutual information, нормировка — среднее арифметическое энтропий (как sklearn)."""
    a = np.unique(np.asarray(a), return_inverse=True)[1]
    b = np.unique(np.asarray(b), return_inverse=True)[1]
    n = len(a)
    av, bv = np.bincount(a).astype(float), np.bincount(b).astype(float)
    if len(av) == len(bv) == 1:
        return 1.0
    c = _contingency(a, b)
    nij = c.data
    mi = float((nij / n * (np.log(nij * n) - np.log(av[c.row]) - np.log(bv[c.col]))).sum())
    ha = float(-(av / n * np.log(av / n)).sum())
    hb = float(-(bv / n * np.log(bv / n)).sum())
    emi = _emi(av.astype(int), bv.astype(int), n)
    denom = (ha + hb) / 2 - emi
    if abs(denom) < np.finfo(float).eps:
        denom = np.finfo(float).eps if denom >= 0 else -np.finfo(float).eps
    return float((mi - emi) / denom) + 0.0


def same_partition(a: np.ndarray, b: np.ndarray) -> bool:
    c = _contingency(a, b)
    return c.nnz == c.shape[0] == c.shape[1]


def cluster_metrics(codes: np.ndarray, D: Data, U, wcc: np.ndarray) -> dict:
    ua, ub, uw = U
    sizes = np.bincount(codes)
    seeds = np.bincount(codes, weights=D.is_seed.astype(float))
    return {
        "modularity_U": modularity(codes, ua, ub, uw, D.n),
        "internal_turnover_share": float(D.w[codes[D.s] == codes[D.d]].sum() / D.total) if D.total else float("nan"),
        "n_clusters_ge2_seed": int((seeds >= 2).sum()),
        "n_clusters": int((sizes > 0).sum()),
        "largest_cluster": int(sizes.max()),
        "ami_vs_wcc": ami(codes, wcc),
    }


def clusters_block(D: Data, nr: pd.DataFrame, seed: int, n_random: int) -> dict:
    rng = np.random.default_rng(seed)
    U = undirected_projection(D)
    A = sparse.coo_matrix((np.ones(len(D.s)), (D.s, D.d)), shape=(D.n, D.n))
    _, wcc = connected_components(A, directed=True, connection="weak")
    ours = _codes(nr.cluster.to_numpy())
    res = {
        "ours": cluster_metrics(ours, D, U, wcc),
        "wcc": cluster_metrics(wcc, D, U, wcc),
    }
    runs = [cluster_metrics(_codes(rng.permutation(ours)), D, U, wcc) for _ in range(n_random)]
    res["random_same_sizes"] = {k: _band([r[k] for r in runs]) for k, _, _, _ in CLUSTER_METRICS}
    identical = same_partition(ours, wcc)
    res["ours"]["identical_to_wcc"] = identical

    labels = {k: dat for k, _, _, dat in CLUSTER_METRICS}
    verdicts, summary = {}, []
    for dummy in ("wcc", "random_same_sizes"):
        verdicts[dummy] = {k: _verdict(res["ours"][k], res[dummy][k], dr) for k, dr, _, _ in CLUSTER_METRICS}
        line = _summary_line(
            f"clusters (seed {seed}" + (f", {n_random} повторов" if dummy == "random_same_sizes" else "")
            + f"): наши кластеры против {dummy}", verdicts[dummy], labels)
        if dummy == "wcc":
            line += ("; разбиение совпадает со слабосвязными компонентами" if identical else
                     f"; AMI с компонентами {_fmt(res['ours']['ami_vs_wcc'])}")
        summary.append(line)
    return {
        "conditions": {
            "seed": seed, "n_random": n_random,
            "U": "ненаправленная проекция, вес пары = sum(A→B) + sum(B→A)",
            "internal_turnover_share": "Σ sum_kzt направленных рёбер внутри кластеров / общий оборот; "
                                       "у компонент это потолок 1,0 по построению",
            "random_same_sizes": "перестановка меток нашего разбиения: размеры кластеров те же",
            "ami": "поправка на случайное совпадение (Vinh и др., 2010), среднее арифметическое энтропий",
            "missing_cluster_id": "узел без cluster_id считается отдельным кластером",
        },
        "methods": res,
        "verdicts": verdicts,
        "_summary": summary,
    }


# ============================================================ 4. временной флаг

class FastTransitRef:
    """Эталонный флаг: пары «вход A→B, выход B→C», A≠C, выход/вход 0,8–1,2, лаг 0–2 дня;
    узел помечен, если среди допустимых пар ≥2 разных входа и ≥2 разных выхода
    (равносильно паросочетанию 1-к-1 из ≥2 пар)."""

    def __init__(self, D: Data):
        self.n = D.n
        self.days = D.tday
        idx = np.arange(len(D.ts))
        tin = pd.DataFrame({"i": idx, "b": D.td, "a": D.ts})
        tout = pd.DataFrame({"o": idx, "b": D.ts, "c": D.td})
        m = tin.merge(tout, on="b")
        m = m[m.a.to_numpy() != m.c.to_numpy()]
        ai, ao = D.tamt[m.i.to_numpy()], D.tamt[m.o.to_numpy()]
        with np.errstate(divide="ignore", invalid="ignore"):
            r = np.where(ai > 0, ao / ai, np.nan)
        keep = (r >= FT_RATIO[0]) & (r <= FT_RATIO[1])
        self.pi, self.po, self.pb = m.i.to_numpy()[keep], m.o.to_numpy()[keep], m.b.to_numpy()[keep]
        self.m = len(D.ts)

    def flags(self, days: np.ndarray | None = None) -> np.ndarray:
        d = self.days if days is None else days
        lag = d[self.po] - d[self.pi]
        ok = (lag >= FT_LAG[0]) & (lag <= FT_LAG[1])
        if not ok.any():
            return np.zeros(self.n, dtype=bool)
        b = self.pb[ok].astype(np.int64)
        ni = np.bincount(np.unique(b * self.m + self.pi[ok]) // self.m, minlength=self.n)
        no = np.bincount(np.unique(b * self.m + self.po[ok]) // self.m, minlength=self.n)
        return (ni >= FT_MIN_PAIRS) & (no >= FT_MIN_PAIRS)


def temporal_block(D: Data, nr: pd.DataFrame, source: str | None, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    ft = FastTransitRef(D)
    ref = ft.flags()
    days = D.tday
    base = np.argsort(D.ts, kind="stable")
    nulls = {}
    for kind in ("global", "within_sender"):
        vals = np.empty(N_PERM_DATES, dtype=int)
        for k in range(N_PERM_DATES):
            if kind == "global":
                nd = rng.permutation(days)
            else:
                order = np.lexsort((rng.random(len(days)), D.ts))
                nd = np.empty_like(days)
                nd[base] = days[order]
            vals[k] = int(ft.flags(nd).sum())
        nulls[kind] = vals

    def against(obs: int) -> dict:
        return {k: {"mean": float(v.mean()), "sd": float(v.std(ddof=1)),
                    "p": float((1 + (v >= obs).sum()) / (N_PERM_DATES + 1))} for k, v in nulls.items()}

    reference = {"flagged_real_dates": int(ref.sum()), "null": against(int(ref.sum()))}
    cond = {"n_perm": N_PERM_DATES, "seed": seed, "lag_days": list(FT_LAG), "ratio": list(FT_RATIO),
            "min_pairs": FT_MIN_PAIRS,
            "null_global": "перестановка столбца дат по всем переводам",
            "null_within_sender": "перестановка дат внутри переводов одного отправителя",
            "p": "(1 + #нуль ≥ наблюдаемого) / (n_perm + 1)"}
    if source is None:
        return {
            "status": "нет данных для проверки",
            "note": "в nodes_roles.csv нет колонки fast_transit_flag и фразы «быстрый транзит» в evidence; "
                    "ниже справочно эталонное определение флага на тех же данных",
            "conditions": cond, "reference_only": reference,
            "_summary": [f"temporal: нет данных для проверки (флага нет в выгрузке); справочно эталонный флаг "
                         f"{reference['flagged_real_dates']} узлов против {reference['null']['global']['mean']:.1f} "
                         f"(глобально) и {reference['null']['within_sender']['mean']:.1f} (внутри отправителя) "
                         f"при случайных датах, {N_PERM_DATES} перестановок, seed {seed}"],
        }
    ours = nr.ft_flag.to_numpy(bool)
    obs = int(ours.sum())
    inter, union = int((ours & ref).sum()), int((ours | ref).sum())
    null = against(obs)
    worse = [k for k, v in null.items() if obs <= v["mean"]]
    better = [k for k, v in null.items() if v["p"] <= 0.05]
    verdict = ("лучше" if len(better) == 2 else "хуже" if len(worse) == 2 else "смешанно")
    return {
        "status": "ok", "source": source, "conditions": cond,
        "observed_flagged": obs, "null": null,
        "agreement_with_reference": {"reference_flagged": int(ref.sum()), "both": inter,
                                     "only_csv": int((ours & ~ref).sum()), "only_reference": int((~ours & ref).sum()),
                                     "jaccard": inter / union if union else 1.0},
        "reference": reference, "verdict": verdict,
        "_summary": [f"temporal ({N_PERM_DATES} перестановок, seed {seed}): наш флаг против случайных дат: "
                     f"{verdict}; помечено {obs} узлов против {null['global']['mean']:.1f} (глобально, "
                     f"p={null['global']['p']:.3f}) и {null['within_sender']['mean']:.1f} (внутри отправителя, "
                     f"p={null['within_sender']['p']:.3f}); совпадение с эталонным определением: "
                     f"Жаккар {inter / union if union else 1.0:.2f}"],
    }


# ============================================================ запуск

def run_baselines(data_dir, out_dir, seed: int = 42, n_random: int = 20, role_fn: RoleFn | None = None) -> dict:
    t0 = time.perf_counter()
    data_dir, out_dir = Path(data_dir), Path(out_dir)
    D = load_data(data_dir)
    nr, nr_info = read_nodes_roles(out_dir / "nodes_roles.csv", D)
    top = read_top(out_dir / "top_nodes.csv")
    clusters_csv = out_dir / "clusters.csv"
    timing = {}

    def stage(name, t):
        timing[name] = round(time.perf_counter() - t, 3)
        return time.perf_counter()

    t = stage("load", t0)
    prio = priority_block(D, nr, top, seed, n_random)
    t = stage("priority", t)
    roles = roles_block(D, nr, seed, n_random, role_fn)
    t = stage("roles", t)
    clus = clusters_block(D, nr, seed, n_random)
    t = stage("clusters", t)
    temp = temporal_block(D, nr, nr_info["fast_transit_source"], seed)
    stage("temporal", t)

    blocks = {"priority": prio, "roles": roles, "clusters": clus, "temporal": temp}
    summary = [line for b in blocks.values() for line in b.pop("_summary")]
    warnings = []
    if nr_info["priority_unique"] <= 1:
        warnings.append("priority_score постоянен: порядок «ours» вырожден (по gid)")
    if roles["methods"]["ours"]["outside_vocabulary"]:
        warnings.append(f"{roles['methods']['ours']['outside_vocabulary']} узлов с ролью вне словаря ТЗ")
    if nr_info["gid_missing"]:
        warnings.append(f"в nodes_roles.csv нет {nr_info['gid_missing']} узлов из nodes.parquet")
    report = {
        "baselines": blocks,
        "summary": summary,
        "warnings": warnings,
        "inputs": {
            "data_dir": str(data_dir), "out_dir": str(out_dir), "seed": seed, "n_random": n_random,
            "role_fn": getattr(role_fn, "__qualname__", None) if role_fn else None,
            "nodes_roles": nr_info, "top_nodes_rows": None if top is None else int(len(top)),
            "clusters_csv_rows": int(len(pd.read_csv(clusters_csv))) if clusters_csv.exists() else None,
            "edges_dropped_unknown_gid": D.dropped_edges, "tx_dropped_unknown_gid": D.dropped_tx,
        },
        "timing_s": timing,
        "elapsed_s": round(time.perf_counter() - t0, 3),
    }
    return _jsonable(report)


# ============================================================ печать

def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, dict) and "median" in v:
        return f"{_fmt(v['median'])} [{_fmt(v['p5'])}–{_fmt(v['p95'])}]"
    if isinstance(v, bool):
        return "да" if v else "нет"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    if isinstance(v, (float, np.floating)):
        if math.isnan(v):
            return "—"
        if abs(v) < 5e-4:
            return "0.000"
        if abs(v) >= 2:
            return str(int(v)) if float(v).is_integer() else f"{v:.1f}"
        return f"{v:.3f}"
    return str(v)


def _table(rows: list[list[str]], head: list[str]) -> str:
    w = [max(len(str(r[i])) for r in rows + [head]) for i in range(len(head))]
    line = lambda r: "  ".join(str(c).ljust(w[i]) for i, c in enumerate(r))
    return "\n".join([line(head), line(["-" * x for x in w])] + [line(r) for r in rows])


def print_report(rep: dict) -> None:
    b = rep["baselines"]
    p = b["priority"]
    c = p["conditions"]
    print(f"\n=== priority: изъятие топ-N (seed {c['seed']}, случайные: медиана [5–95 %] по {c['n_random']} "
          f"повторам; LCC до изъятия {c['lcc_before']}, seed {c['n_seed']})")
    keys = [k for k, _, _, _ in PRIO_METRICS]
    head = ["метод", "N", "снятый оборот", "LCC", "seed-ветви", "depth4", "evid≠∅", "evid#"]
    rows = []
    for m in p["outcomes"]:
        for N, o in p["outcomes"][m].items():
            rows.append([m, N] + [_fmt(o[k]) for k in keys])
    print(_table(rows, head))
    print("\nвердикты (наш скор против dummy, по всем N):")
    rows = [[d] + [v[k]["overall"] for k in keys] for d, v in p["verdicts"].items()]
    print(_table(rows, ["dummy", "оборот↑", "LCC↓", "seed↑", "depth4↓", "evid≠∅↑", "evid#↑"]))

    r = b["roles"]["methods"]
    print("\n=== roles")
    keys = ["depth4_terminal", "noise_role_change_share", "share_non_peripheral", "entropy_bits",
            "agreement_with_single_feature", "kappa_with_single_feature"]
    rows = [[m] + [_fmt(r[m].get(k)) for k in keys] for m in r]
    print(_table(rows, ["метод", "terminal@d4↓", "шум ±5 %↓", "не periph", "энтропия", "совп. single", "каппа"]))
    if "noise_note" in r["ours"]:
        print(f"  ours: шум — {r['ours']['noise_note']}")

    cl = b["clusters"]["methods"]
    print("\n=== clusters")
    keys = [k for k, _, _, _ in CLUSTER_METRICS]
    rows = [[m] + [_fmt(cl[m].get(k)) for k in keys] for m in cl]
    print(_table(rows, ["метод", "Q на U↑", "внутр. оборот↑", "≥2 seed", "кластеров", "крупнейший", "AMI с WCC"]))
    print(f"  наше разбиение совпадает с компонентами: {_fmt(cl['ours']['identical_to_wcc'])}")

    t = b["temporal"]
    print(f"\n=== temporal: {t['status']}")
    print("\n=== итог")
    for line in rep["summary"]:
        print(" •", line)
    for w in rep.get("warnings", []):
        print(" ! ", w)
    print(f"\nвремя {rep['elapsed_s']} с; стадии {rep['timing_s']}")


def _load_role_fn(spec: str) -> RoleFn:
    mod, _, attr = spec.partition(":")
    if not attr:
        raise SystemExit("--role-fn: нужен формат пакет.модуль:функция")
    return getattr(importlib.import_module(mod), attr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Сравнение выгрузок с dummy-моделями на прокси-исходах")
    ap.add_argument("--data", required=True, type=Path, help="каталог с nodes/edges/transactions.parquet")
    ap.add_argument("--out", required=True, type=Path, help="каталог с nodes_roles.csv, clusters.csv, top_nodes.csv")
    ap.add_argument("--report", type=Path, default=None, help="куда записать JSON")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--n-random", type=int, default=20, help="повторов для случайных dummy и шума")
    ap.add_argument("--role-fn", default=None, help="пересчёт ролей для шума ±5 %%: пакет.модуль:функция")
    a = ap.parse_args(argv)
    if not (a.out / "nodes_roles.csv").exists():
        print(f"нет {a.out / 'nodes_roles.csv'}", file=sys.stderr)
        return 2
    rep = run_baselines(a.data, a.out, seed=a.seed, n_random=a.n_random,
                        role_fn=_load_role_fn(a.role_fn) if a.role_fn else None)
    print_report(rep)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"отчёт: {a.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
