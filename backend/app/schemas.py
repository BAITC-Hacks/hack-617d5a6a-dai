"""Схемы ответов API «Граф денег». Это контракт с интерфейсом: поля только добавляются, не удаляются.

Все идентификаторы клиентов (gid) передаются строками: значения int64 превышают
Number.MAX_SAFE_INTEGER в JavaScript. В обязательных CSV gid остаётся int64.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["consolidator", "transit", "distributor", "terminal", "coordinator", "peripheral"]


class NodeOut(BaseModel):
    """Узел графа с ролью, приоритетом и наблюдаемыми метриками внутри выгрузки."""

    gid: str = Field(description="Идентификатор клиента строкой (int64 в данных)")
    role: Role = Field(description="Основная роль из словаря ТЗ")
    role_score: float = Field(ge=0, le=1, description="Сила поддержки правила роли, 0–1; не вероятность")
    cluster_id: int = Field(description="Номер кластера из clusters.csv")
    priority_score: float = Field(ge=0, le=1, description="Приоритет проверки для аналитика, 0–1")
    evidence: str = Field(max_length=200, description="Почему такая роль: числа из расчёта, до 200 символов")
    depth: int = Field(ge=0, le=4, description="Колено обхода, 0 = seed")
    is_seed: bool
    in_deg: int = Field(description="От скольких разных клиентов получал")
    out_deg: int = Field(description="Скольким разным клиентам отправлял")
    in_kzt: float = Field(description="Получено внутри графа, KZT")
    out_kzt: float = Field(description="Отправлено внутри графа, KZT")
    in_tx: int
    out_tx: int
    truncated_by_depth: bool = Field(description="Узел на 4-м колене без исходящих: граница выгрузки, не сток")
    priority_raw: float = Field(default=0, description="Сырой скор до нормировки: сумма −ln(доли узлов не ниже) + вес быстрого транзита")
    score_terms: str = Field(default="", description="Два наибольших вклада в скор, например «in_deg=24 (P99, +7.7)»")
    role_checks: str = Field(default="", description="Условия назначенной роли с фактическими значениями, до 200 символов")
    fast_transit_pairs: int = Field(default=0, description="Пар вход→выход 1-к-1 с лагом 0–2 дня и отношением сумм 0,8–1,2")
    fast_transit_flag: bool = Field(default=False, description="Быстрый транзит: пар не меньше двух")
    n_seed_upstream: int = Field(default=0, description="Из скольких seed узел достижим по исходящим переводам")
    betweenness: float = Field(default=0, description="Посредничество в графе выгрузки")
    next_request: str = Field(default="", description="Какой запрос данных закрыл бы главный пробел по узлу")
    limitations: str = Field(default="", description="Ограничения данных по узлу через «; »; пусто, если их нет")
    n_terms_above_p95: int = Field(default=0, description="Сколько из 7 признаков скора в верхних 5 % (вклад ≥ −ln 0,05)")
    in_queue: bool = Field(default=False, description="В очереди проверки: не меньше двух признаков в верхних 5 %")


class EdgeOut(BaseModel):
    """Направленное ребро: агрегат переводов src → dst за период."""

    src: str
    dst: str
    sum_kzt: float
    n_tx: int
    depth: int = Field(description="Колено обхода, на котором найдено ребро (1–4)")


class TransferOut(BaseModel):
    """Отдельный перевод; дата с точностью до дня, порядок внутри дня неизвестен."""

    src: str
    dst: str
    date: date
    sum_kzt: float


class GraphMeta(BaseModel):
    mock: bool = Field(description="True: роли и скоры — заглушка по простым порогам, не результат пайплайна")
    n_nodes: int
    n_edges: int
    truncated: bool = Field(description="True, если список узлов обрезан параметром limit")


class GraphResponse(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut] = Field(description="Только рёбра, у которых оба конца есть в nodes")
    meta: GraphMeta


ChronologyStatus = Literal["вход раньше выхода", "тот же день, порядок неизвестен", "выход раньше входа"]


class TransferPair(BaseModel):
    """Пара переводов через узел: вход A→узел и выход узел→C, A ≠ C.

    Отношение сумм out/in в [0,8; 1,2], |лаг| ≤ 3 дня. Даты с точностью до дня.
    """

    in_src: str = Field(description="Отправитель входящего перевода (gid строкой)")
    out_dst: str = Field(description="Получатель исходящего перевода (gid строкой)")
    in_date: date
    out_date: date
    in_sum: float
    out_sum: float
    lag_days: int = Field(description="День выхода − день входа; отрицательный: выход раньше входа")
    chronology_status: ChronologyStatus
    matched_1to1: bool = Field(description="Пара вошла в быстрый транзит (сопоставление 1-к-1, лаг 0–2 дня)")


class NodeCard(BaseModel):
    """Карточка узла: сам узел, его рёбра, отдельные переводы и пары вход→выход."""

    node: NodeOut
    in_edges: list[EdgeOut]
    out_edges: list[EdgeOut]
    transfers: list[TransferOut] = Field(description="Все переводы с участием узла, по дате")
    pairs: list[TransferPair] = Field(default_factory=list, description="Пары вход→выход узла, по дате входа")


class SearchResponse(BaseModel):
    items: list[NodeOut] = Field(description="Совпадения по началу строки gid, по убыванию priority_score")
    total: int = Field(description="Сколько всего совпадений (items может быть короче из-за limit)")


class TopNode(BaseModel):
    rank: int
    gid: str
    role: Role
    priority_score: float
    why: str = Field(description="Обоснование текстом")
    in_queue: bool = Field(default=False, description="В очереди проверки: не меньше двух признаков в верхних 5 %")


class TopResponse(BaseModel):
    items: list[TopNode]


class ClusterOut(BaseModel):
    cluster_id: int
    n_nodes: int
    n_seed: int
    sum_kzt_internal: float = Field(description="Сумма рёбер, у которых оба конца внутри кластера")
    top_gids: list[str]
    hypothesis: str = Field(description="Гипотеза о назначении кластера, для проверки")


class ClustersResponse(BaseModel):
    items: list[ClusterOut]


class ClusterDetail(BaseModel):
    cluster: ClusterOut
    graph: GraphResponse


class RoleInfo(BaseModel):
    role: Role
    title: str = Field(description="Название по-русски для легенды")
    description: str


class MetaResponse(BaseModel):
    mock: bool
    source: Literal["outputs", "mock"] = Field(description="outputs: CSV пайплайна; mock: заглушка по порогам")
    n_nodes: int
    n_edges: int
    n_transactions: int
    n_seed: int
    n_clusters: int
    period_start: date
    period_end: date
    total_kzt: float
    roles: list[RoleInfo]
    method: str = Field(default="mock", description="Метод пайплайна из run_meta.json (v1, v0) или mock")
    threshold_score: float | None = Field(default=None, description="Порог приоритета на шкале priority_score 0–1")
    threshold_raw: float | None = Field(default=None, description="Порог приоритета на сырой шкале priority_raw")
    elapsed_s: float | None = Field(default=None, description="Время прогона пайплайна, с")
    n_in_queue: int | None = Field(default=None, description="Сколько узлов в очереди проверки (run_meta.json)")
    queue_rule: str | None = Field(default=None, description="Правило очереди проверки текстом (run_meta.json)")


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mock: bool


class ReloadResponse(BaseModel):
    source: Literal["outputs", "mock"]
    n_nodes: int
