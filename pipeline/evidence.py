"""Тексты с числами: evidence узла (≤200 символов), why для топа, hypothesis кластера."""

from __future__ import annotations

import pandas as pd

MAX_LEN = 200


def kzt(v: float) -> str:
    v = float(v)
    if abs(v) >= 1e6:
        return f"{v / 1e6:.1f} млн KZT".replace(".", ",")
    if abs(v) >= 1e3:
        return f"{v / 1e3:.0f} тыс. KZT"
    return f"{v:.0f} KZT"


def _fit(parts: list[str], tail: list[str]) -> str:
    """Склеивает части; хвост (граница выгрузки и т. п.) сохраняется, основа при нужде режется."""
    tail_s = "; ".join(tail)
    base = "; ".join(parts)
    s = base + ("; " + tail_s if tail_s else "")
    if len(s) <= MAX_LEN:
        return s
    room = MAX_LEN - (len(tail_s) + 2 if tail_s else 0)
    return (base[: max(0, room - 1)].rstrip(" ;,") + "…" + ("; " + tail_s if tail_s else ""))[:MAX_LEN]


def node_evidence(r) -> str:
    role = r.role
    if r.isolated:
        parts = [f"v0: переводов в выгрузке нет; глубина {r.depth}"]
    elif role == "consolidator":
        parts = [f"v0: признаки консолидации (fan-in): входов {r.in_deg} на {kzt(r.in_kzt)}",
                 f"выходов {r.out_deg} на {kzt(r.out_kzt)}"]
    elif role == "distributor":
        parts = [f"v0: признаки распределения (fan-out): выходов {r.out_deg} на {kzt(r.out_kzt)}",
                 f"входов {r.in_deg} на {kzt(r.in_kzt)}"]
    elif role == "coordinator":
        parts = [f"v0: признаки gather-scatter: входов {r.in_deg} на {kzt(r.in_kzt)}, "
                 f"выходов {r.out_deg} на {kzt(r.out_kzt)}",
                 f"betweenness {r.betweenness:.4f}"]
    elif role == "transit":
        parts = [f"v0: признаки транзита: вход {kzt(r.in_kzt)}, выход {kzt(r.out_kzt)}",
                 f"доля прохода {r.pass_through:.2f}, входов {r.in_deg}, выходов {r.out_deg}"]
    elif role == "terminal":
        parts = [f"v0: признаки конечного получателя: входов {r.in_deg} на {kzt(r.in_kzt)}",
                 "исходящих в выгрузке 0"]
    else:
        parts = [f"v0: признаков роли мало: входов {r.in_deg} ({kzt(r.in_kzt)}), "
                 f"выходов {r.out_deg} ({kzt(r.out_kzt)})"]
    if r.n_seed_upstream and not r.isolated:
        parts.append(f"достижим от {r.n_seed_upstream} seed")
    tail = []
    if r.depth4_boundary:
        tail.append("граница выгрузки (глубина 4)")
    if r.is_seed:
        tail.append("seed, входы неполны")
    return _fit(parts, tail)


def top_why(r) -> str:
    parts = [f"приоритет {r.priority_score:.4f}: PageRank выше {r.pagerank_pct * 100:.0f}% узлов",
             f"связей {r.in_deg + r.out_deg} (вх {r.in_deg}, исх {r.out_deg})",
             f"оборот {kzt(r.in_kzt + r.out_kzt)}",
             f"роль {r.role}, кластер {r.cluster_id}"]
    tail = []
    if r.depth4_boundary:
        tail.append("граница выгрузки")
    if r.is_seed:
        tail.append("seed")
    return _fit(parts, tail)


def cluster_hypothesis(c) -> str:
    n = c.n_nodes
    head = f"{n} {'узел' if n == 1 else 'узлов'}, {c.n_seed} seed, внутренний оборот {kzt(c.sum_kzt_internal)}"
    if c.in_gid and c.sum_kzt_internal > 0:
        share = c.in_kzt / c.sum_kzt_internal * 100
        mid = f"вход сосредоточен у {c.in_gid} ({kzt(c.in_kzt)}, {share:.0f}% внутреннего оборота)"
    else:
        mid = "внутренних переводов нет"
    return f"{head}; {mid}; {c.n_boundary} узлов на границе выгрузки"


def apply(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["evidence"] = [node_evidence(r) for r in df.itertuples(index=False)]
    return df
