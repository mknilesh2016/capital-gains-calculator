"""
Unit tests for tax calculation.
"""

import pytest
from datetime import datetime

from capital_gains.tax import TaxCalculator, TaxRates
from capital_gains.models import SaleTransaction, IndianGains


class TestTaxRates:
    """Tests for TaxRates class."""
    
    def test_default_rates(self):
        """Test default tax rates."""
        rates = TaxRates()
        
        assert rates.INDIAN_LTCG == 0.1495
        assert rates.FOREIGN_LTCG == 0.1495
        assert rates.INDIAN_STCG == 0.2392
        assert rates.FOREIGN_STCG == 0.39
        assert rates.LTCG_EXEMPTION == 125000.0


class TestTaxCalculator:
    """Tests for TaxCalculator class."""
    
    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return TaxCalculator()
    
    @pytest.fixture
    def sample_transactions(self):
        """Create sample transactions."""
        return [
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2022, 1, 15),
                stock_type="RS",
                symbol="AAPL",
                shares=100,
                sale_price_usd=150.0,
                acquisition_price_usd=120.0,
                gross_proceeds_usd=15000.0,
                capital_gain_inr=300000.0,  # Pre-calculated
                is_long_term=True,
            ),
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2024, 6, 15),
                stock_type="TRADE",
                symbol="VTI",
                shares=50,
                sale_price_usd=250.0,
                acquisition_price_usd=220.0,
                gross_proceeds_usd=12500.0,
                capital_gain_inr=130000.0,  # Pre-calculated
                is_long_term=False,
            ),
        ]
    
    def test_calculate_schwab_gains(self, calculator, sample_transactions):
        """Test calculation of Schwab gains."""
        result = calculator.calculate(transactions=sample_transactions)
        
        assert result.schwab_ltcg == 300000.0
        assert result.schwab_stcg == 130000.0
    
    def test_calculate_indian_gains(self, calculator):
        """Test calculation of Indian gains."""
        indian_gains = [
            IndianGains(source="Indian Stocks", ltcg=200000.0, stcg=50000.0),
            IndianGains(source="Indian Mutual Funds", ltcg=100000.0, stcg=25000.0),
        ]
        
        result = calculator.calculate(indian_gains=indian_gains)
        
        assert result.indian_ltcg == 300000.0
        assert result.indian_stcg == 75000.0
    
    def test_ltcg_exemption_applied(self, calculator):
        """Test LTCG exemption is applied to Indian gains."""
        indian_gains = [
            IndianGains(source="Indian Stocks", ltcg=200000.0, stcg=0.0),
        ]
        
        result = calculator.calculate(indian_gains=indian_gains)
        
        assert result.rebate_used == 125000.0
        assert result.indian_ltcg_after_rebate == 75000.0
    
    def test_ltcg_exemption_capped(self, calculator):
        """Test LTCG exemption is capped at actual Indian LTCG."""
        indian_gains = [
            IndianGains(source="Indian Stocks", ltcg=50000.0, stcg=0.0),
        ]
        
        result = calculator.calculate(indian_gains=indian_gains)
        
        # Exemption capped at 50000 (actual LTCG)
        assert result.rebate_used == 50000.0
        assert result.indian_ltcg_after_rebate == 0.0
    
    def test_tax_calculation_rates(self, calculator, sample_transactions):
        """Test tax is calculated with correct rates."""
        result = calculator.calculate(transactions=sample_transactions)
        
        # Foreign LTCG @ 14.95%
        expected_foreign_ltcg_tax = 300000.0 * 0.1495
        assert result.foreign_ltcg_tax == pytest.approx(expected_foreign_ltcg_tax)
        
        # Foreign STCG @ 39%
        expected_foreign_stcg_tax = 130000.0 * 0.39
        assert result.foreign_stcg_tax == pytest.approx(expected_foreign_stcg_tax)
    
    def test_tax_liability_positive(self, calculator, sample_transactions):
        """Test tax liability when taxes due."""
        result = calculator.calculate(
            transactions=sample_transactions,
            taxes_paid=0.0
        )
        
        assert result.tax_liability > 0
        assert result.tax_liability == result.total_tax
    
    def test_tax_liability_with_prepayment(self, calculator, sample_transactions):
        """Test tax liability reduced by prepayment."""
        result = calculator.calculate(
            transactions=sample_transactions,
            taxes_paid=50000.0
        )
        
        assert result.taxes_paid == 50000.0
        assert result.tax_liability == result.total_tax - 50000.0
    
    def test_tax_refund_when_overpaid(self, calculator, sample_transactions):
        """Test negative liability (refund) when overpaid."""
        result = calculator.calculate(
            transactions=sample_transactions,
            taxes_paid=1000000.0  # Overpaid
        )
        
        assert result.tax_liability < 0  # Refund due
    
    def test_combined_calculation(self, calculator, sample_transactions):
        """Test combined Schwab and Indian calculation."""
        indian_gains = [
            IndianGains(source="Indian Stocks", ltcg=200000.0, stcg=50000.0),
        ]
        
        result = calculator.calculate(
            transactions=sample_transactions,
            indian_gains=indian_gains,
            taxes_paid=100000.0
        )
        
        # Check totals
        assert result.total_ltcg == 500000.0  # 300000 + 200000
        assert result.total_stcg == 180000.0  # 130000 + 50000
        
        # Check tax was calculated
        assert result.total_tax > 0
        assert result.tax_liability == result.total_tax - 100000.0
    
    def test_loss_setoff(self, calculator):
        """Test loss set-off provisions."""
        transactions = [
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2024, 6, 15),
                stock_type="TRADE",
                symbol="VTI",
                shares=50,
                sale_price_usd=200.0,
                acquisition_price_usd=250.0,
                gross_proceeds_usd=10000.0,
                capital_gain_inr=-50000.0,  # Loss
                is_long_term=False,
            ),
        ]
        
        result = calculator.calculate(transactions=transactions)
        
        # Loss should result in zero tax (not negative)
        assert result.foreign_stcg_tax >= 0

