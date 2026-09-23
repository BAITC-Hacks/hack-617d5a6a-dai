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


class NodeCard(BaseModel):
    """Карточка узла: сам узел, его рёбра и отдельные переводы."""

    node: NodeOut
    in_edges: list[EdgeOut]
    out_edges: list[EdgeOut]
    transfers: list[TransferOut] = Field(description="Все переводы с участием узла, по дате")


class SearchResponse(BaseModel):
    items: list[NodeOut] = Field(description="Совпадения по началу строки gid, по убыванию priority_score")
    total: int = Field(description="Сколько всего совпадений (items может быть короче из-за limit)")


class TopNode(BaseModel):
    rank: int
    gid: str
    role: Role
    priority_score: float
    why: str = Field(description="Обоснование текстом")


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


class HealthResponse(BaseModel):
    status: Literal["ok"]
    mock: bool


class ReloadResponse(BaseModel):
    source: Literal["outputs", "mock"]
    n_nodes: int
