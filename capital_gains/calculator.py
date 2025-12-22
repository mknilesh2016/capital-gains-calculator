"""
Capital gains calculation engine.

This module provides the CapitalGainsCalculator class that computes
capital gains in INR for transactions using exchange rates.
"""

from typing import List, Optional
import os

from .models import SaleTransaction
from .exchange_rates import ExchangeRateService


class CapitalGainsCalculator:
    """
    Calculator for computing capital gains in INR.
    
    Converts USD transactions to INR using SBI TT Buy rates
    and calculates capital gains for each transaction.
    
    Attributes:
        exchange_rate_service: Service for fetching exchange rates
        
    Example:
        >>> calculator = CapitalGainsCalculator()
        >>> calculator.load_exchange_rates('sbi_reference_rates.json')
        >>> transactions = calculator.calculate(transactions)
    """
    
    def __init__(self, exchange_rate_service: Optional[ExchangeRateService] = None):
        """
        Initialize the calculator.
        
        Args:
            exchange_rate_service: Optional pre-configured exchange rate service.
                                   If not provided, a new one is created.
        """
        self.exchange_rate_service = exchange_rate_service or ExchangeRateService()
    
    def load_exchange_rates(self, filepath: str) -> bool:
        """
        Load exchange rates from a JSON file.
        
        Args:
            filepath: Path to the SBI rates JSON file
            
        Returns:
            True if loaded successfully
        """
        return self.exchange_rate_service.load_sbi_rates(filepath)
    
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
            use_sbi: Whether to use SBI rates (True) or approximate rates
            sbi_rates_file: Path to SBI rates file (optional)
            
        Returns:
            List of transactions with calculated INR values
            
        The method:
        1. Collects all unique dates from transactions
        2. Fetches exchange rates for those dates
        3. Calculates INR values and capital gains for each transaction
        """
        if not transactions:
            return transactions
        
        print("\n[*] Fetching exchange rates from SBI TT Buy Rates...")
        
        # Load SBI rates if file provided
        if sbi_rates_file and use_sbi:
            if not os.path.exists(sbi_rates_file):
                # Try to find in default location
                script_dir = os.path.dirname(os.path.abspath(__file__))
                parent_dir = os.path.dirname(script_dir)
                sbi_rates_file = os.path.join(parent_dir, "statements", "sbi_reference_rates.json")
            
            print(f"   Source: {sbi_rates_file}")
            self.exchange_rate_service.load_sbi_rates(sbi_rates_file)
        
        # Collect unique dates needed
        dates_needed = set()
        for txn in transactions:
            dates_needed.add(txn.sale_date)
            dates_needed.add(txn.acquisition_date)
        
        # Get exchange rates for all dates
        print("\n   Exchange rates used (SBI TT Buy):")
        for date in sorted(dates_needed):
            rate = self.exchange_rate_service.get_rate(date, use_sbi)
            print(f"   {date.strftime('%Y-%m-%d')}: Rs.{rate:.4f}/USD")
        
        # Calculate gains for each transaction
        for txn in transactions:
            self._calculate_transaction_gains(txn, use_sbi)
        
        return transactions
    
    def _calculate_transaction_gains(
        self,
        txn: SaleTransaction,
        use_sbi: bool = True
    ) -> None:
        """
        Calculate capital gains for a single transaction.
        
        Modifies the transaction in place.
        
        Args:
            txn: Transaction to calculate
            use_sbi: Whether to use SBI rates
        """
        # Get exchange rates
        sale_rate = self.exchange_rate_service.get_rate(txn.sale_date, use_sbi)
        acq_rate = self.exchange_rate_service.get_rate(txn.acquisition_date, use_sbi)
        
        txn.sale_exchange_rate = sale_rate
        txn.acquisition_exchange_rate = acq_rate
        
        # Calculate values in INR
        txn.sale_price_inr = txn.sale_price_usd * sale_rate
        txn.acquisition_price_inr = txn.acquisition_price_usd * acq_rate
        
        # Convert fees to INR using sale date rate
        txn.fees_and_commissions_inr = txn.fees_and_commissions_usd * sale_rate
        
        # Capital gain in USD
        txn.capital_gain_usd = (
            (txn.sale_price_usd - txn.acquisition_price_usd) * txn.shares
            - txn.fees_and_commissions_usd
        )
        
        # Capital gain in INR
        # (Sale Price INR - Acquisition Price INR) * shares - Fees INR
        total_sale_inr = txn.sale_price_inr * txn.shares
        total_acquisition_inr = txn.acquisition_price_inr * txn.shares
        txn.capital_gain_inr = total_sale_inr - total_acquisition_inr - txn.fees_and_commissions_inr
    
    def get_exchange_rates_cache(self):
        """
        Get the cached exchange rates.
        
        Returns:
            Dictionary of date -> rate mappings
        """
        return self.exchange_rate_service.get_cached_rates()
    
    def save_exchange_rates(self, filepath: str) -> None:
        """
        Save exchange rates cache to a file.
        
        Args:
            filepath: Path to save the cache
        """
        self.exchange_rate_service.save_cache_to_file(filepath)

