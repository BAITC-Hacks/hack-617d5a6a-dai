"""Роли v1: правила из спецификации I2; пороги и порядок — только из rules.py.

role_score назначенной роли = среднее по её условиям от min(1, значение/порог), булевы условия дают 0/1;
periphery = THRESHOLDS["peripheral_score"]. role_checks — строка проверок назначенной роли (≤200 символов).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .evidence import plural
from .rules import ROLE_ORDER, THRESHOLDS as T

MAX_CHECKS = 200


def _num(v) -> str:
    v = float(v)
    if v == int(v) and abs(v) < 1e12:
        return str(int(v))
    if abs(v) < 0.1:
        return f"{v:.4f}"
    return f"{v:.2f}"


class Cond:
    """Условие правила: ge — value ≥ thr (вклад min(1, value/thr)); bool — 0/1."""

    __slots__ = ("label", "value", "thr", "kind", "ok", "text")

    def __init__(self, label: str, value, thr=None, kind: str = "ge", ok: bool | None = None, text: str = ""):
        self.label, self.value, self.thr, self.kind, self.text = label, value, thr, kind, text
        self.ok = bool(value >= thr) if ok is None and kind == "ge" else bool(ok)

    def score(self) -> float:
        if self.kind == "ge" and self.thr and self.thr > 0:
            return min(1.0, float(self.value) / float(self.thr))
        return 1.0 if self.ok else 0.0

    def render(self) -> str:
        mark = "✓" if self.ok else "✗"
        if self.text:
            return f"{self.text} {mark}"
        return f"{self.label} {_num(self.value)}≥{_num(self.thr)} {mark}"


def betweenness_threshold(df: pd.DataFrame) -> float:
    k = T["coordinator_betweenness_min_deg"]
    mid = df.loc[(df.in_deg >= k) & (df.out_deg >= k), "betweenness"]
    if mid.empty:
        return math.inf
    return float(np.quantile(mid.to_numpy(float), T["coordinator_betweenness_q"]))


def _conds(role: str, r, bc_thr: float) -> list[Cond] | None:
    """Условия роли, если правило сработало, иначе None."""
    ft = bool(getattr(r, "fast_transit_flag", 0))
    if role == "coordinator":
        a = [Cond("in_deg", r.in_deg, T["coordinator_min_in_deg"]),
             Cond("out_deg", r.out_deg, T["coordinator_min_out_deg"]),
             Cond("seeds", r.n_seed_upstream, T["coordinator_min_seed_upstream"])]
        if all(c.ok for c in a):
            return a
        k = T["coordinator_betweenness_min_deg"]
        b = [Cond("betweenness", r.betweenness, bc_thr,
                  text=f"betweenness {r.betweenness:.4f}≥P99 {bc_thr:.4f}"),
             Cond("in_deg", r.in_deg, k), Cond("out_deg", r.out_deg, k)]
        if all(c.ok for c in b):
            return b
        return None
    if role == "distributor":
        c = [Cond("out_deg", r.out_deg, T["distributor_min_out_deg"])]
        return c if c[0].ok else None
    if role == "consolidator":
        c = [Cond("in_deg", r.in_deg, T["consolidator_min_in_deg"])]
        return c if c[0].ok else None
    if role == "transit":
        if not (r.in_kzt > 0 and r.out_kzt > 0):
            return None
        base = [Cond("in_kzt", 1, kind="bool", ok=True, text="in_kzt>0"),
                Cond("out_kzt", 1, kind="bool", ok=True, text="out_kzt>0")]
        lo, hi = T["transit_ratio_low"], T["transit_ratio_high"]
        ratio = r.out_kzt / r.in_kzt
        in_band = (lo <= ratio <= hi) and not r.is_seed   # у seed входы неполны: отношение не используется
        if in_band:
            return base + [Cond("ratio", 1, kind="bool", ok=True,
                                text=f"out/in {ratio:.2f}∈[{lo:g};{hi:g}]")]
        if ft:
            return base + [Cond("fast", 1, kind="bool", ok=True,
                                text=f"быстрый транзит {plural(int(r.fast_transit_pairs), 'пара', 'пары', 'пар')}")]
        return None
    if role == "terminal":
        ok = (r.in_deg >= T["terminal_min_in_deg"] and r.out_deg == 0
              and r.depth < T["terminal_max_depth_exclusive"] and not r.is_seed)
        if not ok:
            return None
        return [Cond("in_deg", r.in_deg, T["terminal_min_in_deg"]),
                Cond("out_deg", 1, kind="bool", ok=True, text="out_deg 0=0"),
                Cond("depth", 1, kind="bool", ok=True,
                     text=f"depth {int(r.depth)}<{int(T['terminal_max_depth_exclusive'])}"),
                Cond("not_seed", 1, kind="bool", ok=True, text="не seed")]
    return None


def _peripheral_note(r) -> str:
    if r.isolated:
        return "переводов ≥5 000 KZT в выгрузке нет"
    if r.is_seed and r.out_deg == 0:
        return "seed без исходящих: данные неполны"
    if r.depth4_boundary:
        return "граница выгрузки: исходящие не собирались"
    return "правила других ролей не сработали"


def assign_role(r, bc_thr: float) -> tuple[str, float, str]:
    for role in ROLE_ORDER:
        if role == "peripheral":
            break
        conds = _conds(role, r, bc_thr)
        if conds is not None:
            score = sum(c.score() for c in conds) / len(conds)
            assert not math.isnan(score)
            checks = f"{role}:" + ", ".join(c.render() for c in conds)
            return role, round(float(score), 4), checks[:MAX_CHECKS]
    return "peripheral", float(T["peripheral_score"]), f"peripheral:{_peripheral_note(r)}"[:MAX_CHECKS]


def apply(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Возвращает df с role, role_score, role_checks и порог betweenness P99 (для run_meta)."""
    bc_thr = betweenness_threshold(df)
    res = [assign_role(r, bc_thr) for r in df.itertuples(index=False)]
    df = df.copy()
    df["role"] = [x[0] for x in res]
    df["role_score"] = [x[1] for x in res]
    df["role_checks"] = [x[2] for x in res]
    return df, bc_thr
