"""Тексты с числами: evidence узла (≤200 символов), why для топа, hypothesis кластера."""

from __future__ import annotations

import pandas as pd

MAX_LEN = 200


def plural(n: int, one: str, few: str, many: str) -> str:
    """Согласование числа со словом: 1 узел, 4 узла, 63 узла, 11 узлов."""
    n = int(n)
    m10, m100 = abs(n) % 10, abs(n) % 100
    if m10 == 1 and m100 != 11:
        w = one
    elif 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        w = few
    else:
        w = many
    return f"{n} {w}"


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
        parts = [f"v0: признаки получателя без видимых исходящих: входов {r.in_deg} на {kzt(r.in_kzt)}",
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
    head = f"{plural(n, 'узел', 'узла', 'узлов')}, {c.n_seed} seed, внутренний оборот {kzt(c.sum_kzt_internal)}"
    if c.in_gid and c.sum_kzt_internal > 0:
        share = c.in_kzt / c.sum_kzt_internal * 100
        mid = f"вход сосредоточен у {c.in_gid} ({kzt(c.in_kzt)}, {share:.0f}% внутреннего оборота)"
    else:
        mid = "внутренних переводов нет"
    return f"{head}; {mid}; {plural(c.n_boundary, 'узел', 'узла', 'узлов')} на границе выгрузки"


# ------------------------------------------------------------------ v1

TERM_FACT = {
    "in_kzt": lambda v: f"вход {kzt(v)}",
    "out_kzt": lambda v: f"выход {kzt(v)}",
    "pass_kzt": lambda v: f"проход {kzt(v)}",
    "in_deg": lambda v: f"входов {int(v)}",
    "out_deg": lambda v: f"выходов {int(v)}",
    "betweenness": lambda v: f"betweenness {v:.4f}".replace(".", ","),
    "n_seed_upstream": lambda v: f"достижим от {int(v)} seed",
}

REQ_BOUNDARY = "Запросить исходящие переводы клиента за июль 2026: на 4-м шаге их не собирали."
REQ_SEED = "Запросить полные входящие переводы клиента, включая отправителей вне выборки."
REQ_REVERSED = "Запросить остаток перед ранним исходящим переводом и поступления до него."
REQ_FAST = "Запросить назначения сопоставленных платежей и остатки на даты их проведения."
REQ_ISOLATED = "Запросить переводы клиента меньше 5 000 KZT и операции с другими банками за июль."
REQ_DEFAULT = "Запросить выписку и сведения о контрагентах для крупнейших переводов клиента."

LIM_BOUNDARY = "исходящие не выгружены (глубина 4)"
LIM_SEED = "входы неполны (seed)"
LIM_ISOLATED = "переводов в выгрузке нет"
LIM_SAME_DAY = "порядок внутри дня неизвестен"


def _num1(v: float) -> str:
    return f"{v:.1f}".replace(".", ",")


def queue_fragment(r) -> str:
    """«скор 41,2; выше P95 по 2 фактам[; в очереди проверки]» — очередь по числу признаков, не по сумме."""
    n = int(getattr(r, "n_terms_above_p95", 0))
    above = f"выше P95 по {plural(n, 'факту', 'фактам', 'фактам')}" if n > 0 else "фактов выше P95 нет"
    s = f"скор {_num1(r.priority_raw)}; {above}"
    if int(getattr(r, "in_queue", 0)):
        s += "; в очереди проверки"
    return s


def node_evidence_v1(r) -> str:
    from .priority import pct_label, top_terms
    from .rules import ROLE_RU, ROLE_TYPOLOGY

    head = f"{ROLE_RU[r.role]} ({ROLE_TYPOLOGY[r.role]})"
    facts = [f"{TERM_FACT[t](v)} (P{pct_label(p)})" for t, v, p, _ in top_terms(r)]
    first = head + (": " + ", ".join(facts) if facts else "")
    parts = [first, queue_fragment(r)]
    n_ft = int(getattr(r, "fast_transit_pairs", 0))
    if n_ft > 0:
        parts.append(f"быстрый транзит: {plural(n_ft, 'пара', 'пары', 'пар')} за 0–2 дня")
    tail = []
    if r.depth4_boundary:
        tail.append("граница выгрузки")
    if r.is_seed:
        tail.append("seed, входы неполны")
    if r.isolated:
        tail.append("переводов в выгрузке нет")
    return _fit(parts, tail)


def next_request(r) -> str:
    if r.depth4_boundary:
        return REQ_BOUNDARY
    # все 19 изолятов — seed; без этой строки правило seed их перехватывает, а им нужен запрос про порог 5 000 KZT
    if r.isolated:
        return REQ_ISOLATED
    if r.is_seed:
        return REQ_SEED
    if getattr(r, "has_reversed_pair", False):
        return REQ_REVERSED
    if getattr(r, "fast_transit_flag", False):
        return REQ_FAST
    return REQ_DEFAULT


def limitations(r) -> str:
    lim = []
    if r.depth4_boundary:
        lim.append(LIM_BOUNDARY)
    if r.is_seed:
        lim.append(LIM_SEED)
    if r.isolated:
        lim.append(LIM_ISOLATED)
    if getattr(r, "has_same_day_pair", False):
        lim.append(LIM_SAME_DAY)
    return "; ".join(lim)


def apply(df: pd.DataFrame, method: str = "v0") -> pd.DataFrame:
    df = df.copy()
    if method == "v1":
        rows = list(df.itertuples(index=False))
        df["evidence"] = [node_evidence_v1(r) for r in rows]
        df["next_request"] = [next_request(r) for r in rows]
        df["limitations"] = [limitations(r) for r in rows]
    else:
        df["evidence"] = [node_evidence(r) for r in df.itertuples(index=False)]
    return df
