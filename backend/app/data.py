"""Загрузка данных для API.

Источник ролей и приоритетов:
  * outputs/nodes_roles.csv, clusters.csv, top_nodes.csv — результат пайплайна (source="outputs");
  * если их нет — заглушка по простым порогам на реальных gid из task/data (source="mock").

Заглушка нужна интерфейсу, чтобы работать на настоящих идентификаторах до готовности
пайплайна. Её роли и скоры — не результат анализа; ответы помечены mock=true.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DAI_DATA_DIR", ROOT / "task" / "data"))
OUTPUTS_DIR = Path(os.environ.get("DAI_OUTPUTS_DIR", ROOT / "outputs"))

ROLES = ["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]

ROLE_INFO = [
    ("consolidator", "Консолидатор", "Аккумулирует средства от нескольких участников"),
    ("transit", "Транзит", "Пропускает средства дальше, не удерживая"),
    ("distributor", "Распределитель", "Веерная рассылка средств многим получателям"),
    ("terminal", "Конечный получатель", "Деньги приходят и, по наблюдаемым данным, не уходят"),
    ("coordinator", "Координатор", "Структурно важный узел, кандидат в организаторы"),
    ("peripheral", "Периферия", "Признаков роли не выявлено"),
]

NODE_COLUMNS = [
    "gid", "role", "role_score", "cluster_id", "priority_score", "evidence",
    "depth", "is_seed", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
    "truncated_by_depth",
]


@dataclass
class Store:
    mock: bool
    source: str
    nodes: pd.DataFrame          # индекс — gid (str); колонки NODE_COLUMNS
    edges: pd.DataFrame          # src, dst (str), sum_kzt, n_tx, depth
    tx: pd.DataFrame             # src, dst (str), date (date), sum_kzt
    clusters: pd.DataFrame       # cluster_id, n_nodes, n_seed, sum_kzt_internal, top_gids (list[str]), hypothesis
    top: pd.DataFrame            # rank, gid (str), role, priority_score, why
    graph: nx.DiGraph            # узлы — gid (str)
    period_start: date
    period_end: date
    total_kzt: float
    n_seed: int


# ------------------------------------------------------------------ загрузка parquet

def _load_raw(data_dir: Path):
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")
    tx["date"] = pd.to_datetime(tx["date"]).dt.date
    return edges, nodes, tx


def _build_graph(edges: pd.DataFrame, gids: list[str]) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(gids)
    for r in edges.itertuples(index=False):
        g.add_edge(r.src, r.dst, sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return g


def _features(g: nx.DiGraph, nodes: pd.DataFrame) -> pd.DataFrame:
    """Те же базовые метрики, что в стартовом коде организаторов; gid — строкой."""
    df = nodes[["gid", "depth", "is_seed"]].copy()
    df["in_deg"] = df.gid.map(dict(g.in_degree())).fillna(0).astype(int)
    df["out_deg"] = df.gid.map(dict(g.out_degree())).fillna(0).astype(int)
    df["in_kzt"] = df.gid.map(dict(g.in_degree(weight="sum_kzt"))).fillna(0.0).astype(float)
    df["out_kzt"] = df.gid.map(dict(g.out_degree(weight="sum_kzt"))).fillna(0.0).astype(float)
    df["in_tx"] = df.gid.map(dict(g.in_degree(weight="n_tx"))).fillna(0).astype(int)
    df["out_tx"] = df.gid.map(dict(g.out_degree(weight="n_tx"))).fillna(0).astype(int)
    df["pagerank"] = df.gid.map(nx.pagerank(g, weight="sum_kzt")).fillna(0.0)
    df["truncated_by_depth"] = (df.depth == 4) & (df.out_deg == 0)
    return df


# ------------------------------------------------------------------ заглушка

def _mock_role(r) -> tuple[str, float]:
    """Простые пороги на признаках стартового кода. Порядок выбора: сверху вниз."""
    ratio = r.out_kzt / r.in_kzt if r.in_kzt > 0 else np.nan
    if r.in_deg >= 3 and r.out_deg >= 5:
        return "coordinator", min(1.0, (r.in_deg / 6 + r.out_deg / 10) / 2)
    if r.out_deg >= 10:
        return "distributor", min(1.0, r.out_deg / 25)
    if r.in_deg >= 3:
        return "consolidator", min(1.0, r.in_deg / 8)
    if r.in_kzt > 0 and r.out_kzt > 0 and 0.8 <= ratio <= 1.2:
        return "transit", round(1 - abs(ratio - 1) / 0.2, 3)
    if r.in_deg > 0 and r.out_deg == 0 and r.depth < 4:
        return "terminal", 0.5
    return "peripheral", 0.3


def _mock_evidence(r, role: str) -> str:
    s = (f"mock {role}: in_deg={r.in_deg}, out_deg={r.out_deg}, in_kzt={r.in_kzt:,.0f}, "
         f"out_kzt={r.out_kzt:,.0f}, depth={r.depth}, seed={int(r.is_seed)}")
    if r.truncated_by_depth:
        s += ", граница выгрузки"
    return s[:200]


def _mock_clusters(g: nx.DiGraph) -> dict[str, int]:
    """Кластер заглушки = слабосвязная компонента; изоляты — отдельные кластеры."""
    comps = sorted(nx.weakly_connected_components(g), key=lambda c: (-len(c), min(c)))
    return {gid: i for i, comp in enumerate(comps) for gid in comp}


def _mock_outputs(feat: pd.DataFrame, g: nx.DiGraph, edges: pd.DataFrame):
    df = feat.copy()
    roles = [_mock_role(r) for r in df.itertuples(index=False)]
    df["role"] = [x[0] for x in roles]
    df["role_score"] = [round(float(x[1]), 3) for x in roles]
    df["cluster_id"] = df.gid.map(_mock_clusters(g)).astype(int)
    # приоритет заглушки: ранг pagerank и суммарной степени, seed — небольшой сдвиг
    pr_rank = df.pagerank.rank(pct=True)
    deg_rank = (df.in_deg + df.out_deg).rank(pct=True)
    df["priority_score"] = (0.5 * pr_rank + 0.4 * deg_rank + 0.1 * df.is_seed.astype(float)).round(4)
    df["evidence"] = [_mock_evidence(r, r.role) for r in df.itertuples(index=False)]

    # clusters
    rows = []
    e = edges.copy()
    cl = df.set_index("gid").cluster_id
    e["c_src"] = e.src.map(cl)
    e["c_dst"] = e.dst.map(cl)
    internal = e[e.c_src == e.c_dst].groupby("c_src").sum_kzt.sum()
    for cid, grp in df.groupby("cluster_id"):
        top = grp.sort_values("priority_score", ascending=False).gid.head(5).tolist()
        n_seed = int(grp.is_seed.sum())
        vol = float(internal.get(cid, 0.0))
        rows.append({
            "cluster_id": int(cid), "n_nodes": int(len(grp)), "n_seed": n_seed,
            "sum_kzt_internal": vol, "top_gids": top,
            "hypothesis": f"mock: слабосвязная компонента, {len(grp)} узлов, {n_seed} seed, внутренний оборот {vol:,.0f} KZT",
        })
    clusters = pd.DataFrame(rows).sort_values("cluster_id").reset_index(drop=True)

    # top
    top = df.sort_values(["priority_score", "gid"], ascending=[False, True]).head(20).reset_index(drop=True)
    top = pd.DataFrame({
        "rank": np.arange(1, len(top) + 1), "gid": top.gid, "role": top.role,
        "priority_score": top.priority_score, "why": top.evidence,
    })
    return df, clusters, top


# ------------------------------------------------------------------ результат пайплайна

def _outputs_present(out_dir: Path) -> bool:
    return all((out_dir / f).exists() for f in ("nodes_roles.csv", "clusters.csv", "top_nodes.csv"))


def _load_outputs(out_dir: Path, feat: pd.DataFrame):
    roles = pd.read_csv(out_dir / "nodes_roles.csv", dtype={"gid": "int64"})
    roles["gid"] = roles.gid.astype(str)
    keep = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
    df = feat.merge(roles[keep], on="gid", how="left")
    if df.role.isna().any():
        missing = int(df.role.isna().sum())
        raise ValueError(f"nodes_roles.csv: нет строк для {missing} узлов из nodes.parquet")
    df["evidence"] = df.evidence.fillna("").astype(str).str.slice(0, 200)
    df["cluster_id"] = df.cluster_id.astype(int)

    clusters = pd.read_csv(out_dir / "clusters.csv")
    clusters["top_gids"] = clusters.top_gids.fillna("").astype(str).map(
        lambda s: [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]
    )
    clusters["hypothesis"] = clusters.hypothesis.fillna("").astype(str)

    top = pd.read_csv(out_dir / "top_nodes.csv", dtype={"gid": "int64"})
    top["gid"] = top.gid.astype(str)
    top["why"] = top.why.fillna("").astype(str)
    return df, clusters, top


# ------------------------------------------------------------------ точка входа

def load_store(data_dir: Path = DATA_DIR, out_dir: Path = OUTPUTS_DIR) -> Store:
    edges, nodes, tx = _load_raw(data_dir)
    for frame, cols in ((edges, ("src", "dst")), (nodes, ("gid",)), (tx, ("src", "dst"))):
        for c in cols:
            frame[c] = frame[c].astype("int64").astype(str)
    nodes = nodes.sort_values("gid").reset_index(drop=True)
    g = _build_graph(edges, nodes.gid.tolist())
    feat = _features(g, nodes)

    if _outputs_present(out_dir):
        df, clusters, top = _load_outputs(out_dir, feat)
        mock, source = False, "outputs"
    else:
        df, clusters, top = _mock_outputs(feat, g, edges)
        mock, source = True, "mock"

    df = df[NODE_COLUMNS].set_index("gid", drop=False)
    df.index.name = None  # gid остаётся колонкой; индекс без имени, чтобы sort_values не путал их
    return Store(
        mock=mock, source=source, nodes=df, edges=edges, tx=tx.sort_values(["date", "src", "dst"]),
        clusters=clusters, top=top, graph=g,
        period_start=min(tx.date), period_end=max(tx.date),
        total_kzt=float(edges.sum_kzt.sum()), n_seed=int(nodes.is_seed.sum()),
    )
