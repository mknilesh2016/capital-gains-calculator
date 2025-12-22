"""
Unit tests for capital gains calculator.
"""

import pytest
from datetime import datetime

from capital_gains.calculator import CapitalGainsCalculator
from capital_gains.exchange_rates import ExchangeRateService
from capital_gains.models import SaleTransaction


class TestCapitalGainsCalculator:
    """Tests for CapitalGainsCalculator class."""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator with mock exchange rates."""
        service = ExchangeRateService()
        service.sbi_rates = {
            "2025-04-15": 85.0,
            "2023-01-15": 82.0,
        }
        return CapitalGainsCalculator(exchange_rate_service=service)
    
    @pytest.fixture
    def sample_transaction(self):
        """Create a sample transaction."""
        return SaleTransaction(
            sale_date=datetime(2025, 4, 15),
            acquisition_date=datetime(2023, 1, 15),
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
            fees_and_commissions_usd=10.0,
            holding_period_days=820,
            is_long_term=True
        )
    
    def test_calculate_single_transaction(self, calculator, sample_transaction):
        """Test calculating gains for a single transaction."""
        transactions = [sample_transaction]
        
        result = calculator.calculate(transactions, use_sbi=True)
        
        assert len(result) == 1
        txn = result[0]
        
        # Check exchange rates were applied
        assert txn.sale_exchange_rate == 85.0
        assert txn.acquisition_exchange_rate == 82.0
        
        # Check INR values
        assert txn.sale_price_inr == 150.0 * 85.0  # 12750.0
        assert txn.acquisition_price_inr == 120.0 * 82.0  # 9840.0
        
        # Check fees converted
        assert txn.fees_and_commissions_inr == 10.0 * 85.0  # 850.0
        
        # Check capital gain calculation
        # (150 - 120) * 100 - 10 = 2990 USD
        assert txn.capital_gain_usd == pytest.approx(2990.0)
        
        # (12750 * 100) - (9840 * 100) - 850 = 290150 INR
        expected_gain_inr = (12750.0 * 100) - (9840.0 * 100) - 850.0
        assert txn.capital_gain_inr == pytest.approx(expected_gain_inr)
    
    def test_calculate_multiple_transactions(self, calculator):
        """Test calculating gains for multiple transactions."""
        transactions = [
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2023, 1, 15),
                stock_type="RS",
                symbol="AAPL",
                shares=50,
                sale_price_usd=150.0,
                acquisition_price_usd=120.0,
                gross_proceeds_usd=7500.0,
            ),
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2023, 1, 15),
                stock_type="ESPP",
                symbol="AAPL",
                shares=30,
                sale_price_usd=150.0,
                acquisition_price_usd=130.0,
                gross_proceeds_usd=4500.0,
            ),
        ]
        
        result = calculator.calculate(transactions, use_sbi=True)
        
        assert len(result) == 2
        assert all(t.capital_gain_inr != 0 for t in result)
    
    def test_calculate_with_approximate_rates(self, calculator):
        """Test calculation falls back to approximate rates."""
        # Use date not in SBI rates
        txn = SaleTransaction(
            sale_date=datetime(2024, 7, 15),  # Not in mock rates
            acquisition_date=datetime(2022, 1, 15),  # Not in mock rates
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
        )
        
        result = calculator.calculate([txn], use_sbi=False)
        
        assert len(result) == 1
        # Should use approximate rates
        assert result[0].sale_exchange_rate > 0
        assert result[0].acquisition_exchange_rate > 0
    
    def test_get_exchange_rates_cache(self, calculator, sample_transaction):
        """Test getting cached exchange rates."""
        calculator.calculate([sample_transaction], use_sbi=True)
        
        cache = calculator.get_exchange_rates_cache()
        
        assert "2025-04-15" in cache
        assert "2023-01-15" in cache
    
    def test_empty_transactions(self, calculator):
        """Test handling empty transaction list."""
        result = calculator.calculate([], use_sbi=True)
        
        assert result == []

