"""Запись трёх CSV (gid int64, атомарно через os.replace) и outputs/run_meta.json."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pandas as pd

NODE_REQUIRED = ["gid", "role", "role_score", "cluster_id", "priority_score", "evidence"]
NODE_EXTRA = ["is_seed", "depth", "in_deg", "out_deg", "in_kzt", "out_kzt", "in_tx", "out_tx",
              "pass_kzt", "pass_through", "pagerank", "betweenness", "n_seed_upstream",
              "active_days", "first_date", "last_date", "truncated_by_depth", "flags"]
CLUSTER_REQUIRED = ["cluster_id", "n_nodes", "n_seed", "sum_kzt_internal", "top_gids", "hypothesis"]
CLUSTER_EXTRA = ["n_edges_internal", "share_depth4"]
TOP_REQUIRED = ["rank", "gid", "role", "priority_score", "why"]
TOP_EXTRA = ["cluster_id"]


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _atomic_csv(df: pd.DataFrame, path: Path) -> None:
    _atomic_text(path, df.to_csv(index=False, lineterminator="\n"))


def nodes_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df[NODE_REQUIRED + NODE_EXTRA].copy()
    out["gid"] = out.gid.astype("int64")
    out["cluster_id"] = out.cluster_id.astype(int)
    out["role_score"] = out.role_score.round(4)
    out["priority_score"] = out.priority_score.round(4)
    for c in ("in_kzt", "out_kzt", "pass_kzt"):
        out[c] = out[c].round(2)
    out["pass_through"] = out.pass_through.round(4)
    out["pagerank"] = out.pagerank.round(8)
    out["betweenness"] = out.betweenness.round(8)
    return out.sort_values("gid", kind="mergesort").reset_index(drop=True)


def write_all(out_dir: Path, nodes: pd.DataFrame, clusters: pd.DataFrame, top: pd.DataFrame,
              meta: dict) -> list[Path]:
    out_dir = Path(out_dir)
    paths = [out_dir / "nodes_roles.csv", out_dir / "clusters.csv", out_dir / "top_nodes.csv"]
    _atomic_csv(nodes_frame(nodes), paths[0])
    c = clusters[CLUSTER_REQUIRED + CLUSTER_EXTRA].copy()
    _atomic_csv(c, paths[1])
    t = top[TOP_REQUIRED + TOP_EXTRA].copy()
    t["gid"] = t.gid.astype("int64")
    _atomic_csv(t, paths[2])
    _atomic_text(out_dir / "run_meta.json", json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    return paths + [out_dir / "run_meta.json"]
