"""Приоритет v0: ранги PageRank и суммарной степени плюс сдвиг для seed."""

from __future__ import annotations

import pandas as pd

from .rules import THRESHOLDS as T


def v0(df: pd.DataFrame) -> pd.Series:
    pr_rank = df.pagerank.rank(pct=True)
    deg_rank = (df.in_deg + df.out_deg).rank(pct=True)
    s = (T["priority_w_pagerank"] * pr_rank + T["priority_w_degree"] * deg_rank
         + T["priority_w_seed"] * df.is_seed.astype(float))
    return s.clip(0, 1).round(4)


def apply(df: pd.DataFrame, method: str = "v0") -> pd.DataFrame:
    if method != "v0":
        raise NotImplementedError(f"priority method {method!r} ещё не реализован")
    df = df.copy()
    df["priority_score"] = v0(df)
    df["pagerank_pct"] = df.pagerank.rank(pct=True)
    return df
