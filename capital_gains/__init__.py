"""
Capital Gains Calculator Package

A comprehensive Python tool for calculating capital gains from stock sales,
designed for Indian residents with investments in both foreign (US) and Indian markets.

Also includes Schedule FA (Foreign Assets) generation for ITR filing.
"""

__version__ = "1.1.0"

from .models import SaleTransaction, StockLot, IndianGains, TaxData, QuarterlyData
from .calculator import CapitalGainsCalculator
from .exchange_rates import ExchangeRateService
from .tax import TaxCalculator, TaxRates
from .interfaces import (
    IExchangeRateProvider,
    ITransactionParser,
    IIndianGainsParser,
    IGainsCalculator,
    ITaxCalculator,
    IReporter,
    BaseTransactionParser,
    BaseReporter,
)

# Schedule FA imports
from .schedule_fa import (
    ScheduleFAGenerator,
    ScheduleFAConfig,
    ScheduleFAReport,
    ForeignAssetEntry,
    ForeignCustodialAccount,
    StockDataCache,
    StockPriceFetcher,
)

__all__ = [
    # Models
    "SaleTransaction",
    "StockLot", 
    "IndianGains",
    "TaxData",
    "QuarterlyData",
    # Services
    "CapitalGainsCalculator",
    "ExchangeRateService",
    "TaxCalculator",
    "TaxRates",
    # Interfaces
    "IExchangeRateProvider",
    "ITransactionParser",
    "IIndianGainsParser",
    "IGainsCalculator",
    "ITaxCalculator",
    "IReporter",
    "BaseTransactionParser",
    "BaseReporter",
    # Schedule FA
    "ScheduleFAGenerator",
    "ScheduleFAConfig",
    "ScheduleFAReport",
    "ForeignAssetEntry",
    "ForeignCustodialAccount",
    "StockDataCache",
    "StockPriceFetcher",
]

