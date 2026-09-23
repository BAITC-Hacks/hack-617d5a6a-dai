"""Кластеры: Louvain на явной ненаправленной проекции U (вес пары = сумма обоих направлений)."""

from __future__ import annotations

import networkx as nx
import pandas as pd


def build_projection(g: nx.DiGraph) -> nx.Graph:
    """Явная проекция: to_undirected() оставил бы одно из двух встречных рёбер и потерял бы сумму."""
    u = nx.Graph()
    u.add_nodes_from(sorted(g.nodes))
    for a, b, d in sorted(g.edges(data=True), key=lambda x: (x[0], x[1])):
        w = float(d["sum_kzt"])
        if u.has_edge(a, b):
            u[a][b]["sum_kzt"] += w
        else:
            u.add_edge(a, b, sum_kzt=w)
    total_g = sum(d["sum_kzt"] for _, _, d in g.edges(data=True))
    total_u = sum(d["sum_kzt"] for _, _, d in u.edges(data=True))
    assert abs(total_g - total_u) < 1.0, f"сумма весов U {total_u:.2f} != G {total_g:.2f}"
    return u


def assign(g: nx.DiGraph, seed: int = 42, resolution: float = 1.0) -> dict[int, int]:
    u = build_projection(g)
    connected = u.subgraph([n for n in u.nodes if u.degree(n) > 0])
    comms = nx.community.louvain_communities(connected, weight="sum_kzt", resolution=resolution, seed=seed)
    parts: list[set[int]] = []
    for c in comms:
        for comp in nx.connected_components(u.subgraph(c)):
            parts.append(set(comp))
    for n in u.nodes:
        if u.degree(n) == 0:
            parts.append({n})
    parts.sort(key=lambda c: (-len(c), min(c)))
    mapping = {n: i for i, c in enumerate(parts) for n in c}
    assert len(mapping) == g.number_of_nodes(), "не все узлы получили cluster_id"
    return mapping


def cluster_table(df: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Агрегаты по кластерам (без текстов): внутренний оборот, вход, граница выгрузки."""
    cl = df.set_index("gid").cluster_id
    e = edges.assign(c_src=edges.src.map(cl), c_dst=edges.dst.map(cl))
    inner = e[e.c_src == e.c_dst]
    internal = inner.groupby("c_src").sum_kzt.sum()
    n_int = inner.groupby("c_src").size()
    rows = []
    for cid, grp in df.groupby("cluster_id", sort=True):
        top = grp.sort_values(["priority_score", "gid"], ascending=[False, True]).gid.head(5).tolist()
        inn = inner[inner.c_dst == cid].groupby("dst").sum_kzt.sum()
        if len(inn):
            inn = inn.sort_index().sort_values(ascending=False, kind="mergesort")
            in_gid, in_kzt = str(int(inn.index[0])), float(inn.iloc[0])
        else:
            in_gid, in_kzt = "", 0.0
        rows.append({
            "cluster_id": int(cid),
            "n_nodes": int(len(grp)),
            "n_seed": int(grp.is_seed.sum()),
            "sum_kzt_internal": round(float(internal.get(cid, 0.0)), 2),
            "top_gids_list": top,
            "n_edges_internal": int(n_int.get(cid, 0)),
            "n_boundary": int(grp.depth4_boundary.sum()),
            "share_depth4": round(float((grp.depth == 4).mean()), 4),
            "in_gid": in_gid,
            "in_kzt": in_kzt,
        })
    return pd.DataFrame(rows)
