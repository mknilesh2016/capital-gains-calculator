"""
Persistent cache for stock metadata and prices.
Stores data in a JSON file for reuse across runs.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, Tuple


class StockDataCache:
    """
    Persistent cache for stock metadata and prices.
    
    Stores:
    - Metadata: Company name, address, sector, etc.
    - Prices: Historical closing prices by date
    - Peak prices: Peak prices for specific holding periods
    """
    
    def __init__(self, cache_file: str = "stock_cache.json"):
        self.cache_file = Path(cache_file)
        self._data: Dict[str, Any] = {
            'metadata': {},   # symbol -> {name, description, address, city, zip, country}
            'prices': {},     # symbol -> {date_str: price}
            'peak_prices': {},  # symbol -> {period_key: {price, date}}
        }
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from file."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    loaded = json.load(f)
                    self._data.update(loaded)
            except Exception:
                pass  # Use empty cache if load fails
    
    def save_cache(self):
        """Save cache to file."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self._data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save cache: {e}")
    
    def get_metadata(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached metadata for a symbol."""
        return self._data.get('metadata', {}).get(symbol)
    
    def set_metadata(self, symbol: str, metadata: Dict[str, Any]):
        """Set metadata for a symbol."""
        if 'metadata' not in self._data:
            self._data['metadata'] = {}
        self._data['metadata'][symbol] = metadata
    
    def get_price(self, symbol: str, date_str: str) -> Optional[float]:
        """Get cached price for a symbol on a date."""
        prices = self._data.get('prices', {}).get(symbol, {})
        return prices.get(date_str)
    
    def set_price(self, symbol: str, date_str: str, price: float):
        """Set price for a symbol on a date."""
        if 'prices' not in self._data:
            self._data['prices'] = {}
        if symbol not in self._data['prices']:
            self._data['prices'][symbol] = {}
        self._data['prices'][symbol][date_str] = price
    
    def get_peak_price(self, symbol: str, period_key: str) -> Tuple[Optional[float], Optional[str]]:
        """Get cached peak price for a period."""
        peak = self._data.get('peak_prices', {}).get(symbol, {}).get(period_key)
        if peak:
            return peak.get('price'), peak.get('date')
        return None, None
    
    def set_peak_price(self, symbol: str, period_key: str, price: float, date_str: str):
        """Set peak price for a period."""
        if 'peak_prices' not in self._data:
            self._data['peak_prices'] = {}
        if symbol not in self._data['peak_prices']:
            self._data['peak_prices'][symbol] = {}
        self._data['peak_prices'][symbol][period_key] = {'price': price, 'date': date_str}
    
    def has_symbol(self, symbol: str) -> bool:
        """Check if symbol is in cache."""
        return symbol in self._data.get('metadata', {})
    
    def get_cached_symbols(self) -> list:
        """Get list of cached symbols."""
        return list(self._data.get('metadata', {}).keys())
    
    def clear(self):
        """Clear all cached data."""
        self._data = {
            'metadata': {},
            'prices': {},
            'peak_prices': {},
        }

