"""
Stock price fetcher using Yahoo Finance with caching support.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple, Any

from .stock_cache import StockDataCache
from .models import ScheduleFAConfig

# Try to import yfinance
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


class StockPriceFetcher:
    """
    Fetches stock prices from Yahoo Finance with persistent caching.
    
    Features:
    - Fetches and caches company metadata
    - Fetches historical prices
    - Calculates peak prices for holding periods
    - Uses persistent cache for subsequent runs
    """
    
    def __init__(self, config: ScheduleFAConfig, cache: StockDataCache):
        self.config = config
        self.cache = cache
        self._history_cache: Dict[str, Any] = {}  # In-memory history cache
        self._metadata_cache: Dict[str, Dict] = {}  # In-memory metadata cache
    
    def _fetch_metadata(self, symbol: str) -> Dict[str, Any]:
        """Fetch and cache stock metadata from Yahoo Finance."""
        # Check persistent cache first
        cached = self.cache.get_metadata(symbol)
        if cached:
            return cached
        
        if not YFINANCE_AVAILABLE:
            return self._get_default_metadata(symbol)
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Extract relevant metadata
            metadata = {
                'name': info.get('shortName') or info.get('longName') or symbol,
                'description': info.get('longName') or info.get('shortName') or symbol,
                'city': info.get('city', ''),
                'state': info.get('state', ''),
                'country': info.get('country', 'USA'),
                'zip': info.get('zip', ''),
                'sector': info.get('sector', ''),
                'industry': info.get('industry', ''),
                'asset_type': 'ETF' if info.get('quoteType') == 'ETF' else 'Stock',
            }
            
            # Build address string
            city = metadata.get('city', '')
            state = metadata.get('state', '')
            if city and state:
                metadata['address'] = f"{city}, {state}"
            elif city:
                metadata['address'] = city
            else:
                metadata['address'] = 'USA'
            
            # Save to persistent cache
            self.cache.set_metadata(symbol, metadata)
            
            return metadata
            
        except Exception:
            return self._get_default_metadata(symbol)
    
    def _get_default_metadata(self, symbol: str) -> Dict[str, Any]:
        """Get default metadata when unable to fetch."""
        return {
            'name': symbol,
            'description': symbol,
            'city': '',
            'state': '',
            'country': 'USA',
            'zip': '',
            'address': 'USA',
            'sector': '',
            'industry': '',
            'asset_type': 'Stock',
        }
    
    def get_metadata(self, symbol: str) -> Dict[str, Any]:
        """Get stock metadata (from cache or fetch)."""
        if symbol not in self._metadata_cache:
            self._metadata_cache[symbol] = self._fetch_metadata(symbol)
        return self._metadata_cache[symbol]
    
    def get_company_info(self, symbol: str) -> Tuple[str, str, str]:
        """
        Get company info tuple (name, address, zip).
        
        Returns:
            Tuple of (company_name, address, zip_code)
        """
        meta = self.get_metadata(symbol)
        return (
            meta.get('name', symbol),
            meta.get('address', 'USA'),
            meta.get('zip', '') or '00000'
        )
    
    def _get_history(self, symbol: str):
        """Get and cache full year history for a symbol."""
        if symbol in self._history_cache:
            return self._history_cache[symbol]
        
        if not YFINANCE_AVAILABLE:
            return None
        
        try:
            ticker = yf.Ticker(symbol)
            # Get full year history plus buffer
            start = self.config.cy_start - timedelta(days=30)
            end = self.config.cy_end + timedelta(days=5)
            hist = ticker.history(start=start, end=end)
            self._history_cache[symbol] = hist
            return hist
        except Exception as e:
            print(f"Warning: Could not fetch history for {symbol}: {e}")
            return None
    
    def get_price(self, symbol: str, date: datetime) -> float:
        """Get stock price for a specific date."""
        date_str = date.strftime('%Y-%m-%d')
        
        # Check persistent cache first
        cached_price = self.cache.get_price(symbol, date_str)
        if cached_price is not None:
            return cached_price
        
        hist = self._get_history(symbol)
        if hist is None or hist.empty:
            return self._get_fallback_price(symbol, date)
        
        try:
            # Find the closest date
            if date_str in hist.index.strftime('%Y-%m-%d').tolist():
                price = hist.loc[hist.index.strftime('%Y-%m-%d') == date_str, 'Close'].iloc[0]
            else:
                # Get the last available price before or on the date
                hist_before = hist[hist.index <= date.strftime('%Y-%m-%d')]
                if not hist_before.empty:
                    price = hist_before['Close'].iloc[-1]
                else:
                    price = hist['Close'].iloc[0]
            
            # Save to persistent cache
            self.cache.set_price(symbol, date_str, float(price))
            return float(price)
            
        except Exception:
            return self._get_fallback_price(symbol, date)
    
    def get_peak_price_for_period(
        self, 
        symbol: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> Tuple[float, datetime]:
        """
        Get peak price and date for a specific holding period.
        
        Args:
            symbol: Stock symbol
            start_date: Start of holding period
            end_date: End of holding period
        
        Returns:
            Tuple of (peak_price, peak_date)
        """
        # Ensure dates are within CY bounds
        effective_start = max(start_date, self.config.cy_start)
        effective_end = min(end_date, self.config.cy_end)
        
        period_key = f"{effective_start.strftime('%Y%m%d')}_{effective_end.strftime('%Y%m%d')}"
        
        # Check persistent cache first
        cached_price, cached_date = self.cache.get_peak_price(symbol, period_key)
        if cached_price is not None and cached_date is not None:
            try:
                return cached_price, datetime.strptime(cached_date, '%Y-%m-%d')
            except Exception:
                pass
        
        hist = self._get_history(symbol)
        if hist is None or hist.empty:
            price = self._get_fallback_price(symbol, effective_end)
            return price, effective_end
        
        try:
            # Filter history for the specific period
            mask = (hist.index >= effective_start.strftime('%Y-%m-%d')) & \
                   (hist.index <= effective_end.strftime('%Y-%m-%d'))
            period_hist = hist[mask]
            
            if period_hist.empty:
                price = self._get_fallback_price(symbol, effective_end)
                return price, effective_end
            
            # Find peak within the period
            peak_idx = period_hist['High'].idxmax()
            peak_price = period_hist.loc[peak_idx, 'High']
            peak_date = peak_idx.to_pydatetime()
            
            # Save to persistent cache
            self.cache.set_peak_price(
                symbol, period_key, float(peak_price), peak_date.strftime('%Y-%m-%d')
            )
            
            return float(peak_price), peak_date
            
        except Exception:
            price = self._get_fallback_price(symbol, effective_end)
            return price, effective_end
    
    def get_peak_price(self, symbol: str) -> Tuple[float, datetime]:
        """Get peak price for the full calendar year."""
        return self.get_peak_price_for_period(
            symbol, self.config.cy_start, self.config.cy_end
        )
    
    def get_closing_price(self, symbol: str) -> float:
        """Get closing price as of Dec 31 of the calendar year."""
        return self.get_price(symbol, self.config.cy_end)
    
    def _get_fallback_price(self, symbol: str, date: datetime) -> float:
        """Fallback price when yfinance is unavailable - uses cache or default."""
        date_str = date.strftime('%Y-%m-%d')
        
        # Check if we have any cached price for this symbol
        cached = self.cache.get_price(symbol, date_str)
        if cached is not None:
            return cached
        
        # Return default value for unknown symbols
        return 100.00
    
    def prefetch_symbols(self, symbols: set) -> Dict[str, bool]:
        """
        Prefetch data for multiple symbols.
        
        Returns dict of {symbol: was_cached}
        """
        results = {}
        for symbol in symbols:
            was_cached = self.cache.has_symbol(symbol)
            self.get_metadata(symbol)
            try:
                self.get_peak_price(symbol)
                self.get_closing_price(symbol)
            except Exception:
                pass
            results[symbol] = was_cached
        return results

