"""Strict data-tool arguments. No model client or persistence in this module."""
from typing import Dict, List, Optional

from pydantic import Field

from .contracts import Contract, RecommendationIntent, RecommendationOptions
from .execution import ToolResult
from .order_contracts import OrderQuery
from .planning import TaskStep


class Empty(Contract):
    pass


class Categories(Contract):
    categories: List[str] = Field(max_length=12)


class Search(Contract):
    intent: RecommendationIntent
    limit: int = Field(default=4, ge=1, le=4)
    options: Optional[RecommendationOptions] = None
    category_scope: Optional[List[str]] = Field(default=None, max_length=6)


class Product(Contract):
    sku_id: int = Field(ge=1, le=2147483647)


class ResolveProduct(Contract):
    name: str = Field(min_length=1, max_length=200)
    product_name: str = Field(min_length=1, max_length=200)


class Orders(Contract):
    query: OrderQuery
    request: str = Field(min_length=1, max_length=1000)


class Explanation(Contract):
    step: TaskStep
    completed: Dict[str, ToolResult] = Field(default_factory=dict, max_length=5)


class Knowledge(Contract):
    query: str = Field(min_length=1, max_length=1600)
    category: Optional[str] = Field(default=None, max_length=40)
    scope: List[str] = Field(default_factory=list, max_length=6)


ARGUMENTS = {
    'get_conversation_context': Empty, 'get_saved_preferences': Empty,
    'validate_categories': Categories, 'search_products': Search, 'recommend_bundle': Search,
    'resolve_product': ResolveProduct, 'get_product_details': Product,
    'get_order_status': Orders, 'explain_recommendations': Explanation,
    'search_knowledge': Knowledge,
}
