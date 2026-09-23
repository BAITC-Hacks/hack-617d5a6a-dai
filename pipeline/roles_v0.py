"""Роли v0: пороги заглушки, перенесённые в pipeline; порядок и пороги — из rules.py."""

from __future__ import annotations

import math

import pandas as pd

from .rules import ROLE_ORDER, THRESHOLDS as T


def _check(role: str, r) -> float | None:
    """Возвращает role_score, если правило роли сработало, иначе None."""
    if role == "coordinator":
        if r.in_deg >= T["coordinator_min_in_deg"] and r.out_deg >= T["coordinator_min_out_deg"]:
            return min(1.0, (r.in_deg / T["coordinator_in_norm"] + r.out_deg / T["coordinator_out_norm"]) / 2)
    elif role == "distributor":
        if r.out_deg >= T["distributor_min_out_deg"]:
            return min(1.0, r.out_deg / T["distributor_out_norm"])
    elif role == "consolidator":
        if r.in_deg >= T["consolidator_min_in_deg"]:
            return min(1.0, r.in_deg / T["consolidator_in_norm"])
    elif role == "transit":
        if r.in_kzt > 0 and r.out_kzt > 0:
            ratio = r.out_kzt / r.in_kzt
            lo, hi = T["transit_ratio_low"], T["transit_ratio_high"]
            if lo <= ratio <= hi:
                half = (hi - lo) / 2
                return max(0.0, 1 - abs(ratio - 1) / half)
    elif role == "terminal":
        if r.in_deg > 0 and r.out_deg == 0 and r.depth < T["terminal_max_depth_exclusive"]:
            return T["terminal_score"]
    elif role == "peripheral":
        return T["peripheral_score"]
    return None


def assign_role(r) -> tuple[str, float]:
    for role in ROLE_ORDER:
        s = _check(role, r)
        if s is not None:
            assert not math.isnan(s)
            return role, round(float(s), 4)
    return "peripheral", T["peripheral_score"]


def apply(df: pd.DataFrame) -> pd.DataFrame:
    res = [assign_role(r) for r in df.itertuples(index=False)]
    df = df.copy()
    df["role"] = [x[0] for x in res]
    df["role_score"] = [x[1] for x in res]
    return df
