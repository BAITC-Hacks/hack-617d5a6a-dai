"""Приоритет: v1 — ECOD-подобная сумма хвостовых вкладов (основной); v0 — ранги PageRank и степени (запасной).

v1: для слагаемого j p_j(x) = доля узлов со значением ≥ x (равные включаются), вклад c_j = −ln p_j;
нулевое значение даёт p = 1 и вклад 0. У граничных узлов глубины 4 вклады out_kzt, out_deg, pass_kzt = 0.
priority_raw = Σ c_j + FAST_TRANSIT_WEIGHT · fast_transit_flag; priority_score = priority_raw / max.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .rules import (BOUNDARY_ZERO_TERMS, FAST_TRANSIT_WEIGHT, PRIORITY_THRESHOLD_RAW, SCORE_TERMS,
                    SCORE_WEIGHTS, THRESHOLDS as T)


def v0(df: pd.DataFrame) -> pd.Series:
    pr_rank = df.pagerank.rank(pct=True)
    deg_rank = (df.in_deg + df.out_deg).rank(pct=True)
    s = (T["priority_w_pagerank"] * pr_rank + T["priority_w_degree"] * deg_rank
         + T["priority_w_seed"] * df.is_seed.astype(float))
    return s.clip(0, 1).round(4)


def tail_share(values: pd.Series) -> np.ndarray:
    """p(x) = доля узлов со значением ≥ x (равные включаются)."""
    x = values.to_numpy(float)
    srt = np.sort(x)
    below = np.searchsorted(srt, x, side="left")
    return (len(x) - below) / len(x)


def _fmt_value(term: str, v: float) -> str:
    if term in ("in_kzt", "out_kzt", "pass_kzt"):
        if v >= 1e6:
            return f"{v / 1e6:.1f}M"
        if v >= 1e3:
            return f"{v / 1e3:.0f}K"
        return f"{v:.0f}"
    if term == "betweenness":
        return f"{v:.4f}"
    return str(int(round(v)))


def pct_label(p: float) -> int:
    """Перцентиль для текста: P = ⌊100·(1 − p)⌋, p — доля узлов со значением ≥ x."""
    return int(math.floor(100 * (1 - p) + 1e-9))


def v1(df: pd.DataFrame) -> pd.DataFrame:
    """Добавляет p_<term>, c_<term>, priority_raw, priority_score, score_terms."""
    df = df.copy()
    boundary = df.depth4_boundary.astype(bool).to_numpy()
    total = np.zeros(len(df))
    for term in SCORE_TERMS:
        p = tail_share(df[term])
        c = -np.log(p) * SCORE_WEIGHTS[term]
        c[df[term].to_numpy(float) <= 0] = 0.0
        if term in BOUNDARY_ZERO_TERMS:
            c[boundary] = 0.0
        c = np.where(np.abs(c) < 1e-12, 0.0, c)
        df[f"p_{term}"] = p
        df[f"c_{term}"] = c
        total += c
    flag = df["fast_transit_flag"].astype(int).to_numpy() if "fast_transit_flag" in df else np.zeros(len(df))
    raw = total + FAST_TRANSIT_WEIGHT * flag
    df["priority_raw"] = np.round(raw, 4)
    mx = float(df.priority_raw.max())
    df["priority_score"] = (df.priority_raw / mx).clip(0, 1).round(4) if mx > 0 else 0.0
    df["score_terms"] = [_score_terms(r) for r in df.itertuples(index=False)]
    return df


def top_terms(r, k: int = 2) -> list[tuple[str, float, float, float]]:
    """Два наибольших вклада: (term, value, p, c); ничьи — в порядке SCORE_TERMS."""
    items = [(t, float(getattr(r, t)), float(getattr(r, f"p_{t}")), float(getattr(r, f"c_{t}")))
             for t in SCORE_TERMS]
    items = [x for x in items if x[3] > 0]
    items.sort(key=lambda x: -round(x[3], 6))
    return items[:k]


def _score_terms(r) -> str:
    return "; ".join(f"{t}={_fmt_value(t, v)} (P{pct_label(p)}, +{c:.1f})" for t, v, p, c in top_terms(r))


def meta_v1(df: pd.DataFrame) -> dict:
    mx = float(df.priority_raw.max())
    return {
        "threshold_raw": PRIORITY_THRESHOLD_RAW,
        "threshold_score": round(PRIORITY_THRESHOLD_RAW / mx, 6) if mx > 0 else None,
        "max_priority_raw": round(mx, 4),
        "n_above_threshold": int((df.priority_raw >= PRIORITY_THRESHOLD_RAW).sum()),
        # справочно: узлы, где ≥2 слагаемых выше P95 (c ≥ −ln 0,05) — буквальное прочтение порога
        "n_two_terms_above_p95": int(((df[[f"c_{t}" for t in SCORE_TERMS]] >= -math.log(0.05) - 1e-9)
                                      .sum(axis=1) >= 2).sum()),
        "weights": {**SCORE_WEIGHTS, "fast_transit_flag": FAST_TRANSIT_WEIGHT},
        "boundary_zero_terms": BOUNDARY_ZERO_TERMS,
    }


def apply(df: pd.DataFrame, method: str = "v1") -> pd.DataFrame:
    df = df.copy()
    df["pagerank_pct"] = df.pagerank.rank(pct=True)
    if method == "v0":
        df["priority_score"] = v0(df)
        return df
    if method == "v1":
        return v1(df)
    raise NotImplementedError(f"priority method {method!r} не реализован")
