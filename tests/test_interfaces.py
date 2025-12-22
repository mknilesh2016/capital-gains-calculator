"""
Unit tests for interface definitions.
"""

import pytest
from datetime import datetime
from typing import List, Dict

from capital_gains.interfaces import (
    IExchangeRateProvider,
    ITransactionParser,
    IIndianGainsParser,
    IGainsCalculator,
    ITaxCalculator,
    IReporter,
    BaseTransactionParser,
    BaseReporter,
)
from capital_gains.models import SaleTransaction, IndianGains, TaxData


class MockExchangeRateProvider:
    """Mock implementation of IExchangeRateProvider for testing."""
    
    def __init__(self, rates: Dict[str, float] = None):
        self.rates = rates or {}
    
    def get_rate(self, date: datetime, use_sbi: bool = True) -> float:
        date_str = date.strftime("%Y-%m-%d")
        return self.rates.get(date_str, 85.0)
    
    def get_rates_for_dates(self, dates: set, use_sbi: bool = True) -> Dict[str, float]:
        return {
            date.strftime("%Y-%m-%d"): self.get_rate(date, use_sbi)
            for date in dates
        }


class MockTransactionParser(BaseTransactionParser):
    """Mock implementation of BaseTransactionParser for testing."""
    
    def parse(self, data, start_date: datetime) -> List[SaleTransaction]:
        return []


class MockReporter(BaseReporter):
    """Mock implementation of BaseReporter for testing."""
    
    def generate(self, transactions, indian_gains=None, tax_data=None, **kwargs):
        return {"report": "generated", "txn_count": len(transactions)}


class TestProtocolCompliance:
    """Tests for Protocol (interface) compliance."""
    
    def test_mock_exchange_rate_provider_is_compliant(self):
        """Test that mock implements IExchangeRateProvider protocol."""
        provider = MockExchangeRateProvider({"2025-04-15": 85.5})
        
        assert isinstance(provider, IExchangeRateProvider)
        
        rate = provider.get_rate(datetime(2025, 4, 15))
        assert rate == 85.5
        
        rates = provider.get_rates_for_dates({datetime(2025, 4, 15)})
        assert "2025-04-15" in rates
    
    def test_mock_parser_is_compliant(self):
        """Test that mock parser implements ITransactionParser protocol."""
        parser = MockTransactionParser()
        
        assert isinstance(parser, ITransactionParser)
        
        result = parser.parse([], datetime(2025, 4, 1))
        assert isinstance(result, list)
    
    def test_base_transaction_parser_long_term_check(self):
        """Test BaseTransactionParser's _is_long_term helper."""
        parser = MockTransactionParser()
        
        # Foreign stocks: >730 days is long term
        assert parser._is_long_term(731) is True
        assert parser._is_long_term(730) is False
        assert parser._is_long_term(365) is False


class TestBaseClasses:
    """Tests for abstract base classes."""
    
    def test_base_transaction_parser_constants(self):
        """Test BaseTransactionParser default constants."""
        assert BaseTransactionParser.LONG_TERM_DAYS == 730
    
    def test_mock_reporter_implements_generate(self):
        """Test that mock reporter implements generate method."""
        reporter = MockReporter()
        
        transactions = [
            SaleTransaction(
                sale_date=datetime(2025, 4, 15),
                acquisition_date=datetime(2023, 1, 15),
                stock_type="RS",
                symbol="AAPL",
                shares=100,
                sale_price_usd=150.0,
                acquisition_price_usd=120.0,
                gross_proceeds_usd=15000.0,
            )
        ]
        
        result = reporter.generate(transactions)
        
        assert result["report"] == "generated"
        assert result["txn_count"] == 1


class TestInterfaceUsability:
    """Tests demonstrating interface usage patterns."""
    
    def test_dependency_injection_pattern(self):
        """Test that interfaces enable dependency injection."""
        
        def calculate_with_provider(
            provider: IExchangeRateProvider,
            date: datetime
        ) -> float:
            """Function that accepts any IExchangeRateProvider."""
            return provider.get_rate(date)
        
        # Can use mock provider
        mock_provider = MockExchangeRateProvider({"2025-04-15": 86.0})
        rate = calculate_with_provider(mock_provider, datetime(2025, 4, 15))
        
        assert rate == 86.0
    
    def test_parser_abstraction(self):
        """Test parser abstraction with interface."""
        
        def process_transactions(
            parser: ITransactionParser,
            data: any,
            start_date: datetime
        ) -> List[SaleTransaction]:
            """Function that accepts any ITransactionParser."""
            return parser.parse(data, start_date)
        
        parser = MockTransactionParser()
        result = process_transactions(parser, [], datetime(2025, 4, 1))
        
        assert isinstance(result, list)


class TestCustomImplementations:
    """Tests for creating custom implementations of interfaces."""
    
    def test_custom_exchange_rate_provider(self):
        """Test creating a custom exchange rate provider."""
        
        class FixedRateProvider:
            """Always returns a fixed rate."""
            
            def __init__(self, fixed_rate: float = 85.0):
                self.fixed_rate = fixed_rate
            
            def get_rate(self, date: datetime, use_sbi: bool = True) -> float:
                return self.fixed_rate
            
            def get_rates_for_dates(self, dates: set, use_sbi: bool = True) -> Dict[str, float]:
                return {d.strftime("%Y-%m-%d"): self.fixed_rate for d in dates}
        
        provider = FixedRateProvider(90.0)
        
        # Should implement the protocol
        assert isinstance(provider, IExchangeRateProvider)
        
        # Should work with any date
        assert provider.get_rate(datetime(2025, 1, 1)) == 90.0
        assert provider.get_rate(datetime(2030, 12, 31)) == 90.0
    
    def test_custom_transaction_parser(self):
        """Test creating a custom transaction parser."""
        
        class SimpleParser(BaseTransactionParser):
            """Simple parser that creates a transaction from each item."""
            
            def parse(self, data: list, start_date: datetime) -> List[SaleTransaction]:
                transactions = []
                for item in data:
                    if item.get("date") >= start_date:
                        transactions.append(SaleTransaction(
                            sale_date=item["date"],
                            acquisition_date=item.get("acq_date", start_date),
                            stock_type="TRADE",
                            symbol=item.get("symbol", "UNKNOWN"),
                            shares=item.get("shares", 0),
                            sale_price_usd=item.get("price", 0.0),
                            acquisition_price_usd=item.get("cost", 0.0),
                            gross_proceeds_usd=item.get("proceeds", 0.0),
                        ))
                return transactions
        
        parser = SimpleParser()
        
        data = [
            {
                "date": datetime(2025, 4, 15),
                "symbol": "TEST",
                "shares": 10,
                "price": 100.0,
                "cost": 80.0,
                "proceeds": 1000.0,
            }
        ]
        
        result = parser.parse(data, datetime(2025, 4, 1))
        
        assert len(result) == 1
        assert result[0].symbol == "TEST"
        assert result[0].shares == 10


