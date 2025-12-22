"""
Unit tests for data models.
"""

import pytest
from datetime import datetime

from capital_gains.models import (
    SaleTransaction,
    StockLot,
    IndianGains,
    TaxData,
    QuarterlyData,
)


class TestSaleTransaction:
    """Tests for SaleTransaction dataclass."""
    
    def test_creation(self):
        """Test basic transaction creation."""
        txn = SaleTransaction(
            sale_date=datetime(2025, 4, 15),
            acquisition_date=datetime(2023, 1, 15),
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
            grant_id="G12345",
            source="EAC"
        )
        
        assert txn.symbol == "AAPL"
        assert txn.shares == 100
        assert txn.sale_price_usd == 150.0
        assert txn.source == "EAC"
    
    def test_get_type_label(self):
        """Test stock type label conversion."""
        txn = SaleTransaction(
            sale_date=datetime(2025, 4, 15),
            acquisition_date=datetime(2023, 1, 15),
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
        )
        
        assert txn.get_type_label() == "RSU"
        
        txn.stock_type = "ESPP"
        assert txn.get_type_label() == "ESPP"
        
        txn.stock_type = "TRADE"
        assert txn.get_type_label() == "Trade"
    
    def test_holding_period_str(self):
        """Test holding period string formatting."""
        txn = SaleTransaction(
            sale_date=datetime(2025, 4, 15),
            acquisition_date=datetime(2023, 1, 15),
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
            holding_period_days=820  # ~2 years 3 months
        )
        
        assert txn.get_holding_period_str() == "2y 3m"
    
    def test_total_properties(self):
        """Test total INR calculation properties."""
        txn = SaleTransaction(
            sale_date=datetime(2025, 4, 15),
            acquisition_date=datetime(2023, 1, 15),
            stock_type="RS",
            symbol="AAPL",
            shares=100,
            sale_price_usd=150.0,
            acquisition_price_usd=120.0,
            gross_proceeds_usd=15000.0,
            sale_price_inr=12750.0,  # 150 * 85
            acquisition_price_inr=9840.0,  # 120 * 82
        )
        
        assert txn.total_sale_inr == 1275000.0  # 100 * 12750
        assert txn.total_acquisition_inr == 984000.0  # 100 * 9840


class TestStockLot:
    """Tests for StockLot dataclass."""
    
    def test_creation(self):
        """Test stock lot creation with auto-remaining."""
        lot = StockLot(
            purchase_date=datetime(2023, 1, 15),
            symbol="VTI",
            quantity=50,
            price=200.0
        )
        
        assert lot.symbol == "VTI"
        assert lot.quantity == 50
        assert lot.remaining == 50  # Auto-initialized
    
    def test_remaining_updates(self):
        """Test that remaining can be updated."""
        lot = StockLot(
            purchase_date=datetime(2023, 1, 15),
            symbol="VTI",
            quantity=50,
            price=200.0
        )
        
        lot.remaining -= 20
        assert lot.remaining == 30


class TestIndianGains:
    """Tests for IndianGains dataclass."""
    
    def test_creation_defaults(self):
        """Test creation with defaults."""
        gains = IndianGains(source="Indian Stocks")
        
        assert gains.source == "Indian Stocks"
        assert gains.ltcg == 0.0
        assert gains.stcg == 0.0
        assert gains.transactions == []
        assert gains.charges == {}
        assert gains.dividends == 0.0
    
    def test_total_property(self):
        """Test total calculation."""
        gains = IndianGains(
            source="Indian Stocks",
            ltcg=50000.0,
            stcg=25000.0
        )
        
        assert gains.total == 75000.0
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        gains = IndianGains(
            source="Indian Stocks",
            ltcg=50000.0,
            stcg=25000.0
        )
        
        d = gains.to_dict()
        assert d['source'] == "Indian Stocks"
        assert d['ltcg'] == 50000.0
        assert d['stcg'] == 25000.0


class TestTaxData:
    """Tests for TaxData dataclass."""
    
    def test_creation_defaults(self):
        """Test creation with defaults."""
        tax = TaxData()
        
        assert tax.schwab_ltcg == 0.0
        assert tax.ltcg_rebate == 125000.0
        assert tax.indian_ltcg_rate == 0.1495
        assert tax.foreign_stcg_rate == 0.39
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        tax = TaxData(
            schwab_ltcg=100000.0,
            schwab_stcg=50000.0,
            total_tax=25000.0
        )
        
        d = tax.to_dict()
        assert d['schwab_ltcg'] == 100000.0
        assert d['schwab_stcg'] == 50000.0
        assert d['total_tax'] == 25000.0


class TestQuarterlyData:
    """Tests for QuarterlyData dataclass."""
    
    def test_creation(self):
        """Test quarterly data creation."""
        q = QuarterlyData(ltcg=100000.0, stcg=50000.0)
        
        assert q.ltcg == 100000.0
        assert q.stcg == 50000.0
        assert q.total == 150000.0

