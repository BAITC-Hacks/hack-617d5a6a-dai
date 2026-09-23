"""Роли v1: правила из спецификации I2; пороги и порядок — только из rules.py.

role_score — сила поддержки правила, не вероятность:
  * назначенная роль: среднее по условиям сработавшей ветки правила; числовое условие даёт перцентильный
    ранг значения среди всех узлов по этому признаку (доля ниже + половина равных, 0–1), булево — 1;
  * периферия: 1 − максимум поддержки по остальным ролям (насколько узел далёк от любого правила); здесь
    невыполненное булево условие даёт 0, числовое — тот же перцентильный ранг.
Округление до 3 знаков. role_checks — строка проверок назначенной роли (≤200 символов).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .evidence import plural
from .rules import FAST_TRANSIT, ROLE_ORDER, THRESHOLDS as T

MAX_CHECKS = 200
# признаки числовых условий: перцентильный ранг считается по всем узлам
PCT_FEATURES = ["in_deg", "out_deg", "n_seed_upstream", "betweenness", "in_kzt", "out_kzt", "fast_transit_pairs"]


def _num(v) -> str:
    v = float(v)
    if v == int(v) and abs(v) < 1e12:
        return str(int(v))
    if abs(v) < 0.1:
        return f"{v:.4f}"
    return f"{v:.2f}"


def pct_rank(values) -> np.ndarray:
    """Перцентильный ранг: (узлов ниже + ½ равных) / N, в [0;1]."""
    x = np.asarray(values, dtype=float)
    srt = np.sort(x)
    below = np.searchsorted(srt, x, side="left")
    le = np.searchsorted(srt, x, side="right")
    return (below + 0.5 * (le - below)) / len(x)


class Cond:
    """Условие правила: ge — value ≥ thr, gt — value > thr (поддержка = перцентильный ранг); bool — 0/1."""

    __slots__ = ("label", "value", "thr", "kind", "ok", "text", "pct")

    def __init__(self, label: str, value, thr=None, kind: str = "ge", ok: bool | None = None, text: str = "",
                 pct: float | None = None):
        self.label, self.value, self.thr, self.kind, self.text, self.pct = label, value, thr, kind, text, pct
        if ok is None and kind == "ge":
            ok = value >= thr
        elif ok is None and kind == "gt":
            ok = value > thr
        self.ok = bool(ok)

    def score(self) -> float:
        if self.kind in ("ge", "gt"):
            return float(self.pct)
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


def _branches(role: str, r, bc_thr: float) -> list[list[Cond]]:
    """Ветки правила роли в порядке проверки; правило сработало, если выполнены все условия ветки."""
    def ge(label, feat, thr, text=""):
        return Cond(label, getattr(r, feat), thr, text=text, pct=getattr(r, f"pr_{feat}"))

    if role == "coordinator":
        k = T["coordinator_betweenness_min_deg"]
        return [
            [ge("in_deg", "in_deg", T["coordinator_min_in_deg"]),
             ge("out_deg", "out_deg", T["coordinator_min_out_deg"]),
             ge("seeds", "n_seed_upstream", T["coordinator_min_seed_upstream"])],
            [ge("betweenness", "betweenness", bc_thr, text=f"betweenness {r.betweenness:.4f}≥P99 {bc_thr:.4f}"),
             ge("in_deg", "in_deg", k), ge("out_deg", "out_deg", k)],
        ]
    if role == "distributor":
        return [[ge("out_deg", "out_deg", T["distributor_min_out_deg"])]]
    if role == "consolidator":
        return [[ge("in_deg", "in_deg", T["consolidator_min_in_deg"])]]
    if role == "transit":
        base = [Cond("in_kzt", r.in_kzt, 0, kind="gt", text="in_kzt>0", pct=r.pr_in_kzt),
                Cond("out_kzt", r.out_kzt, 0, kind="gt", text="out_kzt>0", pct=r.pr_out_kzt)]
        lo, hi = T["transit_ratio_low"], T["transit_ratio_high"]
        ratio = r.out_kzt / r.in_kzt if r.in_kzt > 0 else math.nan
        in_band = bool(lo <= ratio <= hi) and not r.is_seed   # у seed входы неполны: отношение не используется
        n_ft = int(getattr(r, "fast_transit_pairs", 0))
        ft = bool(getattr(r, "fast_transit_flag", 0))
        return [
            base + [Cond("ratio", 1, kind="bool", ok=in_band,
                         text=f"out/in {ratio:.2f}∈[{lo:g};{hi:g}]")],
            base + [Cond("fast", n_ft, FAST_TRANSIT["min_pairs"], ok=ft, pct=r.pr_fast_transit_pairs,
                         text=f"быстрый транзит {plural(n_ft, 'пара', 'пары', 'пар')}")],
        ]
    if role == "terminal":
        return [[ge("in_deg", "in_deg", T["terminal_min_in_deg"]),
                 Cond("out_deg", 1, kind="bool", ok=r.out_deg == 0, text="out_deg 0=0"),
                 Cond("depth", 1, kind="bool", ok=r.depth < T["terminal_max_depth_exclusive"],
                      text=f"depth {int(r.depth)}<{int(T['terminal_max_depth_exclusive'])}"),
                 Cond("not_seed", 1, kind="bool", ok=not r.is_seed, text="не seed")]]
    return []


def _support(conds: list[Cond]) -> float:
    s = sum(c.score() for c in conds) / len(conds)
    assert not math.isnan(s)
    return s


def _peripheral_note(r) -> str:
    if r.isolated:
        return "переводов ≥5 000 KZT в выгрузке нет"
    if r.is_seed and r.out_deg == 0:
        return "seed без исходящих: данные неполны"
    if r.depth4_boundary:
        return "граница выгрузки: исходящие не собирались"
    return "правила других ролей не сработали"


def assign_role(r, bc_thr: float) -> tuple[str, float, str]:
    best_role, best = "", -1.0
    for role in ROLE_ORDER:
        if role == "peripheral":
            break
        for conds in _branches(role, r, bc_thr):
            if all(c.ok for c in conds):
                checks = f"{role}:" + ", ".join(c.render() for c in conds)
                return role, round(_support(conds), 3), checks[:MAX_CHECKS]
            s = _support(conds)
            if s > best:
                best_role, best = role, s
    score = round(min(1.0, max(0.0, 1.0 - best)), 3)
    checks = f"peripheral:{_peripheral_note(r)}; ни одно правило роли не выполнено; ближе всего к {best_role}"
    return "peripheral", score, checks[:MAX_CHECKS]


def apply(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Возвращает df с role, role_score, role_checks и порог betweenness P99 (для run_meta)."""
    bc_thr = betweenness_threshold(df)
    work = df.copy()
    if "fast_transit_pairs" not in work:
        work["fast_transit_pairs"] = 0
    for feat in PCT_FEATURES:
        work[f"pr_{feat}"] = pct_rank(work[feat])
    res = [assign_role(r, bc_thr) for r in work.itertuples(index=False)]
    df = df.copy()
    df["role"] = [x[0] for x in res]
    df["role_score"] = [x[1] for x in res]
    df["role_checks"] = [x[2] for x in res]
    return df, bc_thr
