"""CLI пайплайна: python -m pipeline.run --data task/data --out outputs [--method v1|v0] [--seed 42].

v1 — основной метод (роли roles_v1, приоритет ECOD, быстрый транзит); v0 — запасной (стоп-кран).
"""

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
from . import evidence, export, features, load, priority, roles_v0, roles_v1
from .rules import (FAST_TRANSIT, PRIORITY_THRESHOLD_RAW, QUEUE_MIN_TERMS_ABOVE_P95, ROLE_ORDER, ROLES,
                    THRESHOLDS, TOP_N)

try:
    from . import temporal
except ImportError as _exc:  # модуль пишется параллельно; без него быстрый транзит = 0
    temporal = None
    _TEMPORAL_ERR = _exc


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


def _temporal_features(tx: pd.DataFrame, nodes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """fast_transit_pairs/flag и статусы пар карточки (|лаг| ≤ 3, 0,8–1,2) по всем узлам."""
    gids = nodes.gid.astype("int64")
    if temporal is None:
        print(f"ПРЕДУПРЕЖДЕНИЕ: pipeline.temporal не импортируется ({_TEMPORAL_ERR}); "
              "быстрый транзит = 0 у всех узлов", flush=True)
        out = pd.DataFrame({"gid": gids, "fast_transit_pairs": 0, "fast_transit_flag": False,
                            "has_reversed_pair": False, "has_same_day_pair": False})
        return out, {"available": False}
    ft = temporal.fast_transit(tx, nodes=nodes[["gid"]])
    ft["gid"] = ft.gid.astype("int64")
    p = temporal.all_pairs(tx)
    card = p[p.ratio_ok.to_numpy() & (p.lag_days.abs().to_numpy() <= temporal.CARD_MAX_ABS_LAG)]
    rev = set(card.loc[card.lag_days < 0, "gid"].astype("int64"))
    same = set(card.loc[card.lag_days == 0, "gid"].astype("int64"))
    out = pd.DataFrame({"gid": gids}).merge(ft, on="gid", how="left")
    out["fast_transit_pairs"] = out.fast_transit_pairs.fillna(0).astype(int)
    out["fast_transit_flag"] = out.fast_transit_flag.fillna(False).astype(bool)
    out["has_reversed_pair"] = out.gid.isin(rev)
    out["has_same_day_pair"] = out.gid.isin(same)
    info = {"available": True, **FAST_TRANSIT,
            "n_flagged": int(out.fast_transit_flag.sum()),
            "pairs_total": int(out.fast_transit_pairs.sum()),
            "n_nodes_reversed_pair": len(rev), "n_nodes_same_day_pair": len(same)}
    return out, info


def run(data_dir: Path, out_dir: Path, method: str = "v1", seed: int = 42) -> dict:
    if method not in ("v0", "v1"):
        raise SystemExit(f"--method {method}: доступны v1 и v0")
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
    tf, ft_info = _temporal_features(tx, nodes)
    df = df.merge(tf, on="gid", how="left", validate="one_to_one")
    assert len(df) == stats["n_nodes"]
    print(f"    быстрый транзит: узлов с флагом {int(df.fast_transit_flag.sum())}, "
          f"пар {int(df.fast_transit_pairs.sum())}")
    t("temporal.fast_transit")

    cmap = clusters_mod.assign(g, seed=seed, resolution=1.0)
    df["cluster_id"] = df.gid.map(cmap).astype(int)
    t("clusters.louvain")

    bc_thr = None
    if method == "v1":
        df, bc_thr = roles_v1.apply(df)
        t("roles_v1")
    else:
        df = roles_v0.apply(df)
        t("roles_v0")
    df = priority.apply(df, method)
    t("priority")
    df = evidence.apply(df, method)
    df["method"] = method

    cl = clusters_mod.cluster_table(df, edges)
    cl["top_gids"] = cl.top_gids_list.map(lambda xs: ";".join(str(int(x)) for x in xs))
    cl["hypothesis"] = [evidence.cluster_hypothesis(r) for r in cl.itertuples(index=False)]

    key = "priority_raw" if method == "v1" else "priority_score"
    top = df.sort_values([key, "gid"], ascending=[False, True], kind="mergesort").head(TOP_N)
    top = top.reset_index(drop=True)
    top["rank"] = np.arange(1, len(top) + 1)
    if method == "v1":
        top["why"] = top.evidence
    else:
        top["why"] = [evidence.top_why(r) for r in top.itertuples(index=False)]
    t("evidence")

    # внутренние инварианты до записи
    assert len(df) == stats["n_nodes"] and df.gid.is_unique
    assert df.role.isin(ROLES).all()
    assert df.evidence.str.len().between(1, 200).all()
    assert df.evidence.str.contains(r"\d").all()
    assert int(cl.n_nodes.sum()) == stats["n_nodes"] and int(cl.n_seed.sum()) == stats["n_seed"]
    assert len(top) >= 20
    assert not ((df.role == "terminal") & df.depth4_boundary).any(), "terminal у граничного узла"
    if method == "v1":
        assert not ((df.role == "terminal") & df.is_seed).any(), "terminal у seed"
        assert not df.evidence.str.startswith("v0:").any()
        assert df.in_queue.isin([0, 1]).all()
        assert (df.in_queue == (df.n_terms_above_p95 >= QUEUE_MIN_TERMS_ABOVE_P95).astype(int)).all()
        assert df.role_score.between(0, 1).all()

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
        "fast_transit": ft_info,
    }
    if method == "v1":
        meta.update(priority.meta_v1(df))
        meta["coordinator_betweenness_p99"] = bc_thr
    meta["elapsed_s"] = round(t.elapsed, 3)
    meta["stages_s"] = dict(t.stages)
    written = export.write_all(out_dir, df, cl, top, meta)
    t("export")
    print(f"готово за {t.elapsed:.2f} s: " + ", ".join(str(p) for p in written))
    print("роли: " + ", ".join(f"{k}={v}" for k, v in meta["role_counts"].items()))
    print(f"кластеров: {len(cl)}")
    if method == "v1":
        print(f"очередь проверки: {meta['n_in_queue']} узлов ({meta['queue_rule']}); "
              f"n_terms_above_p95: {meta['n_terms_above_p95_dist']}")
        print(f"справочно: priority_raw ≥ {PRIORITY_THRESHOLD_RAW:g} у {meta['n_above_threshold']} узлов; "
              f"max_priority_raw {meta['max_priority_raw']}; threshold_score {meta['threshold_score']}")
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
    ap.add_argument("--method", default="v1", choices=["v1", "v0"])
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
