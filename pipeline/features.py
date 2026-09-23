"""Признаки узлов на направленном графе G (все узлы nodes.parquet, включая изоляты)."""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd


def build_graph(edges: pd.DataFrame, nodes: pd.DataFrame) -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from(int(x) for x in nodes.gid)
    for r in edges.itertuples(index=False):
        g.add_edge(int(r.src), int(r.dst), sum_kzt=float(r.sum_kzt), n_tx=int(r.n_tx), depth=int(r.depth))
    return g


def _n_seed_upstream(g: nx.DiGraph, seeds: list[int]) -> dict[int, int]:
    cnt = dict.fromkeys(g.nodes, 0)
    for s in seeds:
        for v in nx.descendants(g, s):
            cnt[v] += 1
    return cnt


def compute(g: nx.DiGraph, nodes: pd.DataFrame, tx: pd.DataFrame, timer=None) -> pd.DataFrame:
    df = nodes[["gid", "depth", "is_seed"]].copy()
    gid = df.gid
    df["in_deg"] = gid.map(dict(g.in_degree())).astype(int)
    df["out_deg"] = gid.map(dict(g.out_degree())).astype(int)
    df["in_kzt"] = gid.map(dict(g.in_degree(weight="sum_kzt"))).astype(float)
    df["out_kzt"] = gid.map(dict(g.out_degree(weight="sum_kzt"))).astype(float)
    df["in_tx"] = gid.map(dict(g.in_degree(weight="n_tx"))).astype(int)
    df["out_tx"] = gid.map(dict(g.out_degree(weight="n_tx"))).astype(int)
    df["pass_kzt"] = np.minimum(df.in_kzt, df.out_kzt)
    mx = np.maximum(df.in_kzt, df.out_kzt)
    df["pass_through"] = np.where(mx > 0, df.pass_kzt / mx.where(mx > 0, 1.0), 0.0)
    if timer:
        timer("features.degrees")

    df["pagerank"] = gid.map(nx.pagerank(g, weight="sum_kzt")).astype(float)
    if timer:
        timer("features.pagerank")
    df["betweenness"] = gid.map(nx.betweenness_centrality(g, weight=None, normalized=True)).astype(float)
    if timer:
        timer("features.betweenness")
    seeds = sorted(int(x) for x in nodes.loc[nodes.is_seed, "gid"])
    df["n_seed_upstream"] = gid.map(_n_seed_upstream(g, seeds)).astype(int)
    if timer:
        timer("features.n_seed_upstream")

    # активность по датам переводов (входящих и исходящих)
    act = pd.concat([tx[["src", "date"]].rename(columns={"src": "gid"}),
                     tx[["dst", "date"]].rename(columns={"dst": "gid"})], ignore_index=True)
    a = act.groupby("gid").date.agg(active_days="nunique", first_date="min", last_date="max")
    df["active_days"] = gid.map(a.active_days).fillna(0).astype(int)
    df["first_date"] = gid.map(a.first_date).dt.strftime("%Y-%m-%d").fillna("")
    df["last_date"] = gid.map(a.last_date).dt.strftime("%Y-%m-%d").fillna("")

    df["depth4_boundary"] = (df.depth == 4) & (df.out_deg == 0)
    df["truncated_by_depth"] = df.depth4_boundary
    df["seed_inflow_incomplete"] = df.is_seed.astype(bool)
    df["isolated"] = (df.in_deg == 0) & (df.out_deg == 0)

    def _flags(r) -> str:
        f = []
        if r.depth4_boundary:
            f.append("depth4_boundary")
        if r.seed_inflow_incomplete:
            f.append("seed_inflow_incomplete")
        if r.isolated:
            f.append("isolated")
        return ";".join(f)

    df["flags"] = [_flags(r) for r in df.itertuples(index=False)]
    if timer:
        timer("features.dates_flags")
    return df.reset_index(drop=True)
