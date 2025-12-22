"""
Interface definitions (Protocols) for the Capital Gains Calculator.

This module defines abstract interfaces that enable loose coupling
between components and facilitate testing with mock implementations.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Optional, Any, Protocol, runtime_checkable

from .models import SaleTransaction, IndianGains, TaxData


@runtime_checkable
class IExchangeRateProvider(Protocol):
    """
    Interface for exchange rate providers.
    
    Any class implementing this interface can be used to fetch
    USD-INR exchange rates for a given date.
    """
    
    def get_rate(self, date: datetime, use_sbi: bool = True) -> float:
        """
        Get USD-INR exchange rate for a given date.
        
        Args:
            date: Date for which to get the exchange rate
            use_sbi: Whether to use SBI rates (True) or approximate rates
            
        Returns:
            Exchange rate (INR per USD)
        """
        ...
    
    def get_rates_for_dates(self, dates: set, use_sbi: bool = True) -> Dict[str, float]:
        """
        Get exchange rates for multiple dates.
        
        Args:
            dates: Set of datetime objects
            use_sbi: Whether to use SBI rates
            
        Returns:
            Dictionary mapping date strings to rates
        """
        ...


@runtime_checkable
class ITransactionParser(Protocol):
    """
    Interface for transaction parsers.
    
    Parsers that implement this interface can parse transaction data
    from various sources (Schwab, Indian brokers, etc.).
    """
    
    def parse(self, data: Any, start_date: datetime) -> List[SaleTransaction]:
        """
        Parse transaction data and return sale transactions.
        
        Args:
            data: Transaction data (format depends on implementation)
            start_date: Only include transactions on or after this date
            
        Returns:
            List of SaleTransaction objects
        """
        ...


@runtime_checkable
class IIndianGainsParser(Protocol):
    """
    Interface for Indian gains parsers (stocks, mutual funds).
    """
    
    def parse(self, filepath: str) -> IndianGains:
        """
        Parse the file and return capital gains data.
        
        Args:
            filepath: Path to the input file
            
        Returns:
            IndianGains object with parsed data
        """
        ...


@runtime_checkable
class IGainsCalculator(Protocol):
    """
    Interface for capital gains calculators.
    """
    
    def calculate(
        self,
        transactions: List[SaleTransaction],
        use_sbi: bool = True,
        sbi_rates_file: Optional[str] = None
    ) -> List[SaleTransaction]:
        """
        Calculate capital gains in INR for all transactions.
        
        Args:
            transactions: List of sale transactions
            use_sbi: Whether to use SBI rates
            sbi_rates_file: Path to SBI rates file (optional)
            
        Returns:
            List of transactions with calculated INR values
        """
        ...
    
    def get_exchange_rates_cache(self) -> Dict[str, float]:
        """Get the cached exchange rates."""
        ...


@runtime_checkable
class ITaxCalculator(Protocol):
    """
    Interface for tax calculators.
    """
    
    def calculate(
        self,
        transactions: List[SaleTransaction] = None,
        indian_gains: List[IndianGains] = None,
        taxes_paid: float = 0.0
    ) -> TaxData:
        """
        Calculate complete tax liability.
        
        Args:
            transactions: List of Schwab/foreign stock transactions
            indian_gains: List of Indian gains (stocks, MFs)
            taxes_paid: Taxes already paid during the year
            
        Returns:
            TaxData object with complete tax calculation
        """
        ...


@runtime_checkable
class IReporter(Protocol):
    """
    Interface for report generators.
    """
    
    def generate(
        self,
        transactions: List[SaleTransaction],
        indian_gains: List[IndianGains] = None,
        tax_data: TaxData = None,
        **kwargs
    ) -> Any:
        """
        Generate a report.
        
        Args:
            transactions: List of sale transactions
            indian_gains: List of Indian gains
            tax_data: Tax calculation data
            **kwargs: Additional report-specific arguments
            
        Returns:
            Report output (format depends on implementation)
        """
        ...


class BaseTransactionParser(ABC):
    """
    Abstract base class for transaction parsers.
    
    Provides common functionality for all transaction parsers.
    """
    
    # Holding period threshold for LTCG classification (in days)
    LONG_TERM_DAYS: int = 730  # >2 years for foreign stocks
    
    @abstractmethod
    def parse(self, data: Any, start_date: datetime) -> List[SaleTransaction]:
        """Parse transaction data and return sale transactions."""
        pass
    
    def _is_long_term(self, holding_days: int) -> bool:
        """Check if holding period qualifies as long-term."""
        return holding_days > self.LONG_TERM_DAYS


class BaseReporter(ABC):
    """
    Abstract base class for report generators.
    """
    
    @abstractmethod
    def generate(
        self,
        transactions: List[SaleTransaction],
        indian_gains: List[IndianGains] = None,
        tax_data: TaxData = None,
        **kwargs
    ) -> Any:
        """Generate a report."""
        pass


# Type aliases for cleaner type hints
TransactionList = List[SaleTransaction]
IndianGainsList = List[IndianGains]
ExchangeRateCache = Dict[str, float]


