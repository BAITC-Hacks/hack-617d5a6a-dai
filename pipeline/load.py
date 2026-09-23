"""Загрузка трёх parquet и sanity-check (логика стартового кода task/starter/starter.py)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load(data_dir: Path):
    data_dir = Path(data_dir)
    edges = pd.read_parquet(data_dir / "edges.parquet")
    nodes = pd.read_parquet(data_dir / "nodes.parquet")
    tx = pd.read_parquet(data_dir / "transactions.parquet")

    nodes["gid"] = nodes.gid.astype("int64")
    nodes["depth"] = nodes.depth.astype(int)
    nodes["is_seed"] = nodes.is_seed.astype(bool)
    for c in ("src", "dst"):
        edges[c] = edges[c].astype("int64")
        tx[c] = tx[c].astype("int64")
    edges["sum_kzt"] = edges.sum_kzt.astype(float)
    edges["n_tx"] = edges.n_tx.astype(int)
    edges["depth"] = edges.depth.astype(int)
    tx["date"] = pd.to_datetime(tx["date"])
    tx["sum_kzt"] = tx.sum_kzt.astype(float)

    nodes = nodes.sort_values("gid", kind="mergesort").reset_index(drop=True)
    edges = edges.sort_values(["src", "dst"], kind="mergesort").reset_index(drop=True)
    tx = tx.sort_values(["date", "src", "dst", "sum_kzt"], kind="mergesort").reset_index(drop=True)
    return edges, nodes, tx


def sanity_check(edges: pd.DataFrame, nodes: pd.DataFrame, tx: pd.DataFrame) -> dict:
    """Проверки стартового кода; при расхождении — AssertionError."""
    assert nodes.gid.is_unique, "nodes.gid содержит дубли"
    assert not edges.duplicated(["src", "dst"]).any(), "edges: дубли пар (src, dst)"

    agg = tx.groupby(["src", "dst"]).agg(s=("sum_kzt", "sum"), c=("sum_kzt", "size")).reset_index()
    m = edges.merge(agg, on=["src", "dst"], how="outer", indicator=True)
    assert (m._merge == "both").all(), "edges и transactions не сходятся по парам"
    assert ((m.s - m.sum_kzt).abs() < 0.5).all(), "edges.sum_kzt не равно сумме transactions"
    assert (m.c == m.n_tx).all(), "edges.n_tx не равно числу transactions"

    gids = set(nodes.gid)
    in_edges = set(edges.src) | set(edges.dst)
    assert in_edges <= gids, "в edges есть gid, которых нет в nodes"
    assert (set(tx.src) | set(tx.dst)) <= gids, "в transactions есть gid, которых нет в nodes"

    orphans = gids - in_edges
    return {
        "n_nodes": int(len(nodes)),
        "n_edges": int(len(edges)),
        "n_tx": int(len(tx)),
        "n_seed": int(nodes.is_seed.sum()),
        "n_isolated": int(len(orphans)),
        "total_kzt": float(edges.sum_kzt.sum()),
        "period_start": str(tx.date.min().date()),
        "period_end": str(tx.date.max().date()),
    }
