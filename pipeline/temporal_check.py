"""Перестановочный контроль временного слоя (в основной запуск пайплайна не входит).

python -m pipeline.temporal_check --data task/data [--perm 1000] [--seed 42] [--out <json>] [--dedup]

Четыре статистики — число узлов B, у которых:
  delta_neg   ≥ 2 пар с лагом Δ ∈ {−3, −2, −1} (выход раньше входа, окно 3 дня);
  delta_zero  ≥ 2 пар с Δ = 0 (тот же день, порядок неизвестен);
  delta_1_2   ≥ 2 пар с Δ ∈ {1, 2};
  fast_transit fast_transit_flag из pipeline.temporal: сопоставление 1-к-1, Δ ∈ [0; 2], пар ≥ 2.
Пара = вход A→B и выход B→C, A ≠ C, отношение сумм выход/вход ∈ [0,8; 1,2], Δ = день выхода − день входа.
Для первых трёх статистик без 1-к-1 пары считаются различными по сочетанию (день входа, день выхода)
у узла — трактовка, при которой воспроизводятся числа проверки 23.09 (45 / 31 узел).

Два нуля: перестановка столбца date по всем переводам (граф, суммы и число операций по дням
сохраняются) и перестановка дат внутри отправителя (сохраняется набор дат каждого отправителя).
p = (1 + число перестановок со статистикой ≥ наблюдаемой) / (N + 1), односторонний.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import temporal as T

STATS = {
    "delta_neg": "узлы с ≥2 парами Δ∈[−3;−1]",
    "delta_zero": "узлы с ≥2 парами Δ=0",
    "delta_1_2": "узлы с ≥2 парами Δ∈[1;2]",
    "fast_transit": "узлы с fast_transit_flag (1-к-1, 0–2 дня)",
}
NULLS = {
    "global": "перестановка date глобально",
    "within_sender": "перестановка date внутри отправителя",
}
_DELTA_RANGES = {"delta_neg": (-3, -1), "delta_zero": (0, 0), "delta_1_2": (1, 2)}
_CHUNK = 200


class _Setup:
    """Пары-кандидаты не зависят от дат: строятся один раз, перестановки меняют только лаг."""

    def __init__(self, tx_df: pd.DataFrame):
        t = T.prep_tx(tx_df)
        p = T._pairs_frame(t)
        p = p[T._ratio_ok(p.ratio.to_numpy())].reset_index(drop=True)
        self.n_tx = len(t)
        self.day = (t.day.to_numpy() - t.day.min()).astype(np.int16)   # 0..30
        assert self.day.max() < 32, "окно дат больше 32 дней: ключи (день входа, день выхода) не влезут"
        self.src_code = pd.factorize(t.src)[0].astype(np.int64)
        self.node_code, self.node_index = pd.factorize(p.gid)
        self.n_nodes = len(self.node_index)
        self.in_id = p.in_id.to_numpy()
        self.out_id = p.out_id.to_numpy()
        self.dev = np.round(np.abs(p.ratio.to_numpy() - 1.0), 9)
        self.n_pairs = len(p)

    # --- перестановки ---
    def perm_global(self, rng: np.random.Generator, k: int) -> np.ndarray:
        return rng.permuted(np.broadcast_to(self.day, (k, self.n_tx)), axis=1)

    def perm_within_sender(self, rng: np.random.Generator, k: int) -> np.ndarray:
        by_src = np.argsort(self.src_code, kind="stable")
        code_sorted = self.src_code[by_src].astype(float)
        day_sorted = self.day[by_src]
        order = np.argsort(code_sorted[None, :] + rng.random((k, self.n_tx)), axis=1)
        out = np.empty((k, self.n_tx), dtype=self.day.dtype)
        out[:, by_src] = day_sorted[order]
        return out

    # --- статистики на пачке матриц дней D (k × n_tx) ---
    def stats(self, D: np.ndarray) -> dict[str, np.ndarray]:
        k = D.shape[0]
        din = D[:, self.in_id].astype(np.int64)
        dout = D[:, self.out_id].astype(np.int64)
        lag = dout - din
        res: dict[str, np.ndarray] = {}
        for name, (lo, hi) in _DELTA_RANGES.items():
            pi, qi = np.nonzero((lag >= lo) & (lag <= hi))
            key = ((pi * self.n_nodes + self.node_code[qi]) * 32 + din[pi, qi]) * 32 + dout[pi, qi]
            node_perm = np.unique(key) // 1024          # perm * n_nodes + node, по одной записи на сочетание дней
            cnt = np.bincount(node_perm, minlength=k * self.n_nodes)
            res[name] = (cnt.reshape(k, self.n_nodes) >= T.FAST_MIN_PAIRS).sum(axis=1)
        # быстрый транзит: жадное 1-к-1 внутри узла и внутри перестановки
        pi, qi = np.nonzero((lag >= T.FAST_LAG_MIN) & (lag <= T.FAST_LAG_MAX))
        ki = pi * self.n_tx + self.in_id[qi]
        ko = pi * self.n_tx + self.out_id[qi]
        acc = T.greedy_match(ki, ko, self.out_id[qi], self.in_id[qi], lag[pi, qi], self.dev[qi])
        cnt = np.bincount(pi[acc] * self.n_nodes + self.node_code[qi[acc]], minlength=k * self.n_nodes)
        res["fast_transit"] = (cnt.reshape(k, self.n_nodes) >= T.FAST_MIN_PAIRS).sum(axis=1)
        return res


def run_check(tx_df: pd.DataFrame, n_perm: int = 1000, seed: int = 42) -> dict:
    t0 = time.perf_counter()
    s = _Setup(tx_df)
    obs = {k: int(v[0]) for k, v in s.stats(s.day[None, :]).items()}
    # согласованность с pipeline.temporal.fast_transit
    ft = T.fast_transit(tx_df)
    assert obs["fast_transit"] == int(ft.fast_transit_flag.sum()), "расхождение с temporal.fast_transit"
    t_setup = time.perf_counter() - t0

    rows = []
    null_times = {}
    for ni, (null, fn) in enumerate([("global", s.perm_global), ("within_sender", s.perm_within_sender)]):
        t1 = time.perf_counter()
        rng = np.random.default_rng([seed, ni])
        acc = {k: [] for k in STATS}
        done = 0
        while done < n_perm:
            k = min(_CHUNK, n_perm - done)
            r = s.stats(fn(rng, k))
            for name in STATS:
                acc[name].append(r[name])
            done += k
        for name in STATS:
            x = np.concatenate(acc[name]).astype(float)
            ge = int((x >= obs[name]).sum())
            sd = float(x.std(ddof=1)) if len(x) > 1 else 0.0
            rows.append({
                "stat": name, "label": STATS[name], "null": null, "null_label": NULLS[null],
                "observed": obs[name], "null_mean": round(float(x.mean()), 2), "null_sd": round(sd, 2),
                "null_p05": float(np.percentile(x, 5)), "null_p95": float(np.percentile(x, 95)),
                "n_ge": ge, "p": round((1 + ge) / (len(x) + 1), 4),
                "z": round((obs[name] - float(x.mean())) / sd, 2) if sd > 0 else None,
            })
        null_times[null] = round(time.perf_counter() - t1, 3)
    return {
        "n_perm": n_perm, "seed": seed, "n_tx": s.n_tx, "n_ratio_pairs": s.n_pairs,
        "definitions": {
            "pair": "вход A→B и выход B→C, A≠C, выход/вход ∈ [0.8; 1.2], lag = день выхода − день входа",
            "delta_stats": "≥2 различных сочетаний (день входа, день выхода) у узла, без 1-к-1",
            "fast_transit": "жадное 1-к-1 внутри узла по |отношение−1|, затем лаг; lag 0–2; пар ≥ 2",
            "p": "(1 + #{null ≥ observed}) / (N + 1), односторонний",
        },
        "observed": obs,
        "rows": rows,
        "fast_transit_pairs_total": int(ft.fast_transit_pairs.sum()),
        "elapsed_s": {"setup": round(t_setup, 3), **null_times,
                      "total": round(time.perf_counter() - t0, 3)},
    }


def format_table(res: dict) -> str:
    hdr = f"{'статистика':<44} {'наблюд.':>7} {'контроль':>8} {'sd':>5} {'z':>5} {'p':>7}  тип нуля"
    lines = [hdr, "-" * len(hdr)]
    for r in sorted(res["rows"], key=lambda r: (list(STATS).index(r["stat"]), r["null"])):
        z = "" if r["z"] is None else f"{r['z']:.1f}"
        lines.append(f"{r['label']:<44} {r['observed']:>7d} {r['null_mean']:>8.1f} {r['null_sd']:>5.1f} "
                     f"{z:>5} {r['p']:>7.3f}  {r['null_label']}")
    e = res["elapsed_s"]
    lines.append(f"перестановок {res['n_perm']}, seed {res['seed']}, переводов {res['n_tx']}, "
                 f"пар с отношением 0,8–1,2: {res['n_ratio_pairs']}; время {e['total']:.2f} s "
                 f"(подготовка {e['setup']:.2f}, глобально {e['global']:.2f}, внутри отправителя "
                 f"{e['within_sender']:.2f})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.temporal_check")
    ap.add_argument("--data", type=Path, default=Path("task/data"))
    ap.add_argument("--perm", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=None, help="путь для JSON (по умолчанию только печать)")
    ap.add_argument("--dedup", action="store_true", help="удалить полностью совпадающие строки переводов")
    a = ap.parse_args(argv)
    tx = pd.read_parquet(a.data / "transactions.parquet")
    if a.dedup:
        tx = tx.drop_duplicates().reset_index(drop=True)
    res = run_check(tx, a.perm, a.seed)
    res["dedup"] = bool(a.dedup)
    print(format_table(res))
    js = json.dumps(res, ensure_ascii=False, indent=2)
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(js + "\n", encoding="utf-8")
        print(f"JSON: {a.out}")
    else:
        print(js)
    return 0


if __name__ == "__main__":
    sys.exit(main())
