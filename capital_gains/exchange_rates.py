"""
Exchange rate handling for USD-INR conversions.

This module provides the ExchangeRateService class for fetching and caching
SBI TT Buy rates for currency conversion.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, Optional


class ExchangeRateService:
    """
    Service for handling USD-INR exchange rate lookups.
    
    Uses SBI TT Buy rates as the primary source, with fallback to
    approximate rates for missing dates.
    
    Attributes:
        cache: In-memory cache of date -> rate mappings
        sbi_rates: Loaded SBI rates from JSON file
        
    Example:
        >>> service = ExchangeRateService()
        >>> service.load_sbi_rates('sbi_reference_rates.json')
        >>> rate = service.get_rate(datetime(2025, 4, 15))
        >>> print(rate)
        85.50
    """
    
    # Historical approximate rates by quarter (fallback)
    APPROXIMATE_RATES = {
        (2022, 1): 74.5, (2022, 2): 76.5, (2022, 3): 79.5, (2022, 4): 81.5,
        (2023, 1): 82.5, (2023, 2): 82.0, (2023, 3): 83.0, (2023, 4): 83.0,
        (2024, 1): 83.0, (2024, 2): 83.5, (2024, 3): 83.5, (2024, 4): 84.0,
        (2025, 1): 85.5, (2025, 2): 85.0, (2025, 3): 84.0, (2025, 4): 84.5,
    }
    DEFAULT_RATE = 84.5
    
    def __init__(self):
        """Initialize the exchange rate service."""
        self.cache: Dict[str, float] = {}
        self.sbi_rates: Dict[str, float] = {}
    
    def load_sbi_rates(self, filepath: str) -> bool:
        """
        Load SBI TT Buy rates from a JSON file.
        
        Args:
            filepath: Path to the JSON file containing rates
            
        Returns:
            True if loaded successfully, False otherwise
            
        The JSON file should have format: {"YYYY-MM-DD": rate, ...}
        """
        if not os.path.exists(filepath):
            print(f"  Warning: SBI rates file not found: {filepath}")
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.sbi_rates = json.load(f)
            
            print(f"  [OK] Loaded {len(self.sbi_rates)} SBI TT Buy rates from {os.path.basename(filepath)}")
            return True
        except Exception as e:
            print(f"  Warning: Error reading SBI rates file: {e}")
            return False
    
    def get_rate(self, date: datetime, use_sbi: bool = True) -> float:
        """
        Get USD-INR exchange rate for a given date.
        
        Args:
            date: Date for which to get the exchange rate
            use_sbi: Whether to use SBI rates (True) or only approximate rates
            
        Returns:
            Exchange rate (INR per USD)
            
        The method follows this fallback hierarchy:
        1. Check in-memory cache
        2. Check SBI rates for exact date
        3. Look for next available date (up to 7 days forward)
        4. Look for previous available date (up to 7 days back)
        5. Use approximate quarterly rate
        """
        date_str = date.strftime("%Y-%m-%d")
        
        # Check cache first
        if date_str in self.cache:
            return self.cache[date_str]
        
        if use_sbi and self.sbi_rates:
            # Check SBI rates for exact date
            if date_str in self.sbi_rates:
                rate = self.sbi_rates[date_str]
                self.cache[date_str] = rate
                return rate
            
            # Look for next available date (SBI doesn't publish on weekends/holidays)
            for days_forward in range(1, 8):
                next_date = date + timedelta(days=days_forward)
                next_str = next_date.strftime("%Y-%m-%d")
                if next_str in self.sbi_rates:
                    rate = self.sbi_rates[next_str]
                    self.cache[date_str] = rate
                    return rate
            
            # Fallback: Look for previous date
            for days_back in range(1, 8):
                prev_date = date - timedelta(days=days_back)
                prev_str = prev_date.strftime("%Y-%m-%d")
                if prev_str in self.sbi_rates:
                    rate = self.sbi_rates[prev_str]
                    self.cache[date_str] = rate
                    return rate
        
        # Final fallback to approximate rate
        print(f"  Warning: No SBI rate for {date_str}, using approximate rate")
        rate = self._get_approximate_rate(date)
        self.cache[date_str] = rate
        return rate
    
    def _get_approximate_rate(self, date: datetime) -> float:
        """
        Get approximate USD-INR rate based on historical averages.
        
        Args:
            date: Date for which to get the rate
            
        Returns:
            Approximate exchange rate
        """
        quarter = (date.month - 1) // 3 + 1
        key = (date.year, quarter)
        return self.APPROXIMATE_RATES.get(key, self.DEFAULT_RATE)
    
    def get_rates_for_dates(self, dates: set, use_sbi: bool = True) -> Dict[str, float]:
        """
        Get exchange rates for multiple dates.
        
        Args:
            dates: Set of datetime objects
            use_sbi: Whether to use SBI rates
            
        Returns:
            Dictionary mapping date strings to rates
        """
        rates = {}
        for date in sorted(dates):
            date_str = date.strftime("%Y-%m-%d")
            rates[date_str] = self.get_rate(date, use_sbi)
        return rates
    
    def save_cache_to_file(self, filepath: str) -> None:
        """
        Save the exchange rates cache to a JSON file.
        
        Args:
            filepath: Path to save the cache
        """
        with open(filepath, 'w') as f:
            json.dump(self.cache, f, indent=2, sort_keys=True)
    
    def get_cached_rates(self) -> Dict[str, float]:
        """
        Get all cached exchange rates.
        
        Returns:
            Dictionary of cached date -> rate mappings
        """
        return self.cache.copy()
    
    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self.cache.clear()

