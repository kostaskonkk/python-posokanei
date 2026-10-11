"""Unofficial typed client for the price API behind posokanei.gov.gr."""

from .aclient import AsyncPosoKanei
from .client import PosoKanei
from .errors import (
    APIError,
    ForbiddenError,
    NotFoundError,
    PosoKaneiError,
    RateLimitError,
    SchemaError,
)
from .models import (
    CategoryNode,
    CategoryTree,
    Competitor,
    Competitors,
    DailyPrice,
    DateRange,
    PriceDrop,
    PriceHistory,
    PriceStats,
    Product,
    ProductPage,
    Retailer,
    RetailerPrice,
    Stats,
    VatRate,
)

__version__ = "0.1.0"

__all__ = [
    "APIError",
    "AsyncPosoKanei",
    "CategoryNode",
    "CategoryTree",
    "Competitor",
    "Competitors",
    "DailyPrice",
    "DateRange",
    "ForbiddenError",
    "NotFoundError",
    "PosoKanei",
    "PosoKaneiError",
    "PriceDrop",
    "PriceHistory",
    "PriceStats",
    "Product",
    "ProductPage",
    "RateLimitError",
    "Retailer",
    "RetailerPrice",
    "SchemaError",
    "Stats",
    "VatRate",
    "__version__",
]
