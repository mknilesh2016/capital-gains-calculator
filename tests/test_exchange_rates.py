"""
Unit tests for exchange rate handling.
"""

import pytest
import json
import tempfile
import os
from datetime import datetime

from capital_gains.exchange_rates import ExchangeRateService


class TestExchangeRateService:
    """Tests for ExchangeRateService class."""
    
    @pytest.fixture
    def service(self):
        """Create a fresh service for each test."""
        return ExchangeRateService()
    
    @pytest.fixture
    def sample_rates_file(self):
        """Create a temporary rates file."""
        rates = {
            "2025-04-01": 85.0,
            "2025-04-02": 85.1,
            "2025-04-03": 85.2,
            "2025-04-07": 85.3,  # Skip weekend
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(rates, f)
            filepath = f.name
        
        yield filepath
        
        # Cleanup
        os.unlink(filepath)
    
    def test_load_sbi_rates(self, service, sample_rates_file):
        """Test loading rates from file."""
        result = service.load_sbi_rates(sample_rates_file)
        
        assert result is True
        assert len(service.sbi_rates) == 4
        assert service.sbi_rates["2025-04-01"] == 85.0
    
    def test_load_sbi_rates_missing_file(self, service):
        """Test loading from non-existent file."""
        result = service.load_sbi_rates("/nonexistent/file.json")
        
        assert result is False
        assert len(service.sbi_rates) == 0
    
    def test_get_rate_exact_date(self, service, sample_rates_file):
        """Test getting rate for exact date."""
        service.load_sbi_rates(sample_rates_file)
        
        rate = service.get_rate(datetime(2025, 4, 1))
        assert rate == 85.0
    
    def test_get_rate_weekend_forward(self, service, sample_rates_file):
        """Test getting rate for weekend uses next available."""
        service.load_sbi_rates(sample_rates_file)
        
        # April 5, 2025 is Saturday, should use April 7
        rate = service.get_rate(datetime(2025, 4, 5))
        assert rate == 85.3  # April 7 rate
    
    def test_get_rate_cached(self, service, sample_rates_file):
        """Test that rates are cached."""
        service.load_sbi_rates(sample_rates_file)
        
        # First call
        rate1 = service.get_rate(datetime(2025, 4, 1))
        # Second call should use cache
        rate2 = service.get_rate(datetime(2025, 4, 1))
        
        assert rate1 == rate2
        assert "2025-04-01" in service.cache
    
    def test_get_rate_approximate_fallback(self, service):
        """Test approximate rate fallback."""
        # No SBI rates loaded
        rate = service.get_rate(datetime(2025, 4, 1), use_sbi=True)
        
        # Should fall back to approximate rate for 2025 Q2
        assert rate == 85.0  # From APPROXIMATE_RATES
    
    def test_get_rate_without_sbi(self, service):
        """Test getting rate with SBI disabled."""
        rate = service.get_rate(datetime(2024, 6, 15), use_sbi=False)
        
        # Should use approximate rate for 2024 Q2
        assert rate == 83.5
    
    def test_get_rates_for_dates(self, service, sample_rates_file):
        """Test getting rates for multiple dates."""
        service.load_sbi_rates(sample_rates_file)
        
        dates = {datetime(2025, 4, 1), datetime(2025, 4, 2)}
        rates = service.get_rates_for_dates(dates)
        
        assert rates["2025-04-01"] == 85.0
        assert rates["2025-04-02"] == 85.1
    
    def test_save_and_load_cache(self, service):
        """Test saving cache to file."""
        service.cache = {
            "2025-04-01": 85.0,
            "2025-04-02": 85.1,
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            service.save_cache_to_file(filepath)
            
            with open(filepath, 'r') as f:
                saved = json.load(f)
            
            assert saved["2025-04-01"] == 85.0
            assert saved["2025-04-02"] == 85.1
        finally:
            os.unlink(filepath)
    
    def test_clear_cache(self, service):
        """Test clearing the cache."""
        service.cache = {"2025-04-01": 85.0}
        
        service.clear_cache()
        
        assert len(service.cache) == 0
    
    def test_get_cached_rates_copy(self, service):
        """Test that get_cached_rates returns a copy."""
        service.cache = {"2025-04-01": 85.0}
        
        cached = service.get_cached_rates()
        cached["2025-04-02"] = 86.0  # Modify the copy
        
        # Original should be unchanged
        assert "2025-04-02" not in service.cache

