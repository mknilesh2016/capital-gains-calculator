"""
Capital Gains Calculator Package

A comprehensive Python tool for calculating capital gains from stock sales,
designed for Indian residents with investments in both foreign (US) and Indian markets.
"""

__version__ = "1.0.0"

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
]

