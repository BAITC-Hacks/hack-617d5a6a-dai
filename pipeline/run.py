"""CLI пайплайна: python -m pipeline.run --data task/data --out outputs [--method v0] [--seed 42]."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import networkx as nx
import numpy as np
import pandas as pd

from . import clusters as clusters_mod
from . import evidence, export, features, load, priority, roles_v0
from .rules import ROLE_ORDER, ROLES, THRESHOLDS, TOP_N


class Timer:
    def __init__(self):
        self.t0 = self.last = time.perf_counter()
        self.stages: dict[str, float] = {}

    def __call__(self, name: str) -> None:
        now = time.perf_counter()
        dt = now - self.last
        self.stages[name] = round(dt, 3)
        self.last = now
        print(f"  [{now - self.t0:6.2f} s] {name:<28} {dt:6.2f} s", flush=True)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.t0


def run(data_dir: Path, out_dir: Path, method: str = "v0", seed: int = 42) -> dict:
    if method != "v0":
        raise SystemExit(f"--method {method}: пока реализован только v0")
    t = Timer()
    print(f"pipeline: method={method} seed={seed} data={data_dir} out={out_dir}")

    edges, nodes, tx = load.load(data_dir)
    t("load")
    stats = load.sanity_check(edges, nodes, tx)
    print(f"    узлов {stats['n_nodes']}, рёбер {stats['n_edges']}, переводов {stats['n_tx']}, "
          f"seed {stats['n_seed']}, изолятов {stats['n_isolated']}, оборот {stats['total_kzt']:,.0f} KZT")
    t("sanity_check")

    g = features.build_graph(edges, nodes)
    t("build_graph")
    df = features.compute(g, nodes, tx, timer=t)

    cmap = clusters_mod.assign(g, seed=seed, resolution=1.0)
    df["cluster_id"] = df.gid.map(cmap).astype(int)
    t("clusters.louvain")

    df = roles_v0.apply(df)
    t("roles_v0")
    df = priority.apply(df, method)
    t("priority")
    df = evidence.apply(df)

    cl = clusters_mod.cluster_table(df, edges)
    cl["top_gids"] = cl.top_gids_list.map(lambda xs: ";".join(str(int(x)) for x in xs))
    cl["hypothesis"] = [evidence.cluster_hypothesis(r) for r in cl.itertuples(index=False)]

    top = df.sort_values(["priority_score", "gid"], ascending=[False, True], kind="mergesort").head(TOP_N)
    top = top.reset_index(drop=True)
    top["rank"] = np.arange(1, len(top) + 1)
    top["why"] = [evidence.top_why(r) for r in top.itertuples(index=False)]
    t("evidence")

    # внутренние инварианты до записи
    assert len(df) == stats["n_nodes"] and df.gid.is_unique
    assert df.role.isin(ROLES).all()
    assert df.evidence.str.len().between(1, 200).all()
    assert df.evidence.str.contains(r"\d").all()
    assert int(cl.n_nodes.sum()) == stats["n_nodes"] and int(cl.n_seed.sum()) == stats["n_seed"]
    assert len(top) >= 20

    meta = {
        "method": method,
        "seed": seed,
        "elapsed_s": None,
        "stages_s": None,
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "versions": {"python": sys.version.split()[0], "pandas": pd.__version__,
                     "networkx": nx.__version__, "numpy": np.__version__},
        "n_nodes": stats["n_nodes"], "n_edges": stats["n_edges"], "n_tx": stats["n_tx"],
        "n_seed": stats["n_seed"], "n_isolated": stats["n_isolated"],
        "total_kzt": stats["total_kzt"],
        "period": [stats["period_start"], stats["period_end"]],
        "n_clusters": int(len(cl)),
        "louvain": {"projection": "explicit_undirected_sum", "weight": "sum_kzt", "resolution": 1.0, "seed": seed},
        "thresholds": THRESHOLDS,
        "role_order": ROLE_ORDER,
        "role_counts": {k: int(v) for k, v in df.role.value_counts().sort_index().items()},
    }
    meta["elapsed_s"] = round(t.elapsed, 3)
    meta["stages_s"] = dict(t.stages)
    written = export.write_all(out_dir, df, cl, top, meta)
    t("export")
    print(f"готово за {t.elapsed:.2f} s: " + ", ".join(str(p) for p in written))
    print("роли: " + ", ".join(f"{k}={v}" for k, v in meta["role_counts"].items()))
    print(f"кластеров: {len(cl)}")
    return meta


def _run_check(data_dir: Path, out_dir: Path) -> int:
    if importlib.util.find_spec("pipeline.check") is None:
        print("ПРЕДУПРЕЖДЕНИЕ: pipeline/check.py нет, проверка выгрузок пропущена", flush=True)
        return 0
    mod = importlib.import_module("pipeline.check")
    if not hasattr(mod, "main"):
        print("ПРЕДУПРЕЖДЕНИЕ: в pipeline.check нет main(), проверка пропущена", flush=True)
        return 0
    try:
        rc = mod.main(["--data", str(data_dir), "--out", str(out_dir)])
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return int(rc or 0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.run")
    ap.add_argument("--data", type=Path, default=Path("task/data"))
    ap.add_argument("--out", type=Path, default=Path("outputs"))
    ap.add_argument("--method", default="v0", choices=["v0"])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-check", action="store_true")
    a = ap.parse_args(argv)
    try:
        run(a.data, a.out, a.method, a.seed)
    except Exception:
        traceback.print_exc()
        return 1
    if a.no_check:
        return 0
    return _run_check(a.data, a.out)


if __name__ == "__main__":
    sys.exit(main())
