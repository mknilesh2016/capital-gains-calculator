"""
Schedule FA (Foreign Assets) Module

Generates Schedule FA reports for Indian Income Tax Returns,
covering foreign equity holdings, sales, and dividend income.
"""

from .stock_cache import StockDataCache
from .price_fetcher import StockPriceFetcher
from .generator import ScheduleFAGenerator
from .models import (
    ScheduleFAConfig,
    ForeignAssetEntry,
    ForeignCustodialAccount,
    ScheduleFAReport,
)

__all__ = [
    "StockDataCache",
    "StockPriceFetcher",
    "ScheduleFAGenerator",
    "ScheduleFAConfig",
    "ForeignAssetEntry",
    "ForeignCustodialAccount",
    "ScheduleFAReport",
]

