"""
Unit tests for Schedule FA (Foreign Assets) functionality.
"""

import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from capital_gains.schedule_fa.models import (
    ScheduleFAConfig,
    ForeignAssetEntry,
    ForeignCustodialAccount,
    DividendEntry,
    ScheduleFAReport,
)
from capital_gains.schedule_fa.stock_cache import StockDataCache
from capital_gains.schedule_fa.price_fetcher import StockPriceFetcher
from capital_gains.schedule_fa.generator import ScheduleFAGenerator, ExchangeRateHandler
from capital_gains.parsers.foreign_assets import ForeignAssetsParser


class TestScheduleFAConfig:
    """Tests for ScheduleFAConfig."""
    
    def test_config_initialization(self):
        """Test config initializes with correct values."""
        config = ScheduleFAConfig(calendar_year=2025)
        
        assert config.calendar_year == 2025
        assert config.assessment_year == "2026-27"
        assert config.cy_start == datetime(2025, 1, 1)
        assert config.cy_end == datetime(2025, 12, 31)
        assert config.fy_start == datetime(2025, 4, 1)
        assert config.fy_end == datetime(2026, 3, 31)
    
    def test_config_assessment_year_format(self):
        """Test assessment year format for different years."""
        assert ScheduleFAConfig(2020).assessment_year == "2021-22"
        assert ScheduleFAConfig(2025).assessment_year == "2026-27"
        assert ScheduleFAConfig(2030).assessment_year == "2031-32"


class TestForeignAssetEntry:
    """Tests for ForeignAssetEntry."""
    
    def test_entry_creation(self):
        """Test creating a foreign asset entry."""
        entry = ForeignAssetEntry(
            serial_no=1,
            entity_name="NVIDIA Corporation",
            entity_address="Santa Clara, CA",
            zip_code="95051",
            nature_of_entity="RSU",
            shares=100.0,
            initial_value_inr=1000000.0,
            peak_value_inr=1500000.0,
            closing_value_inr=1200000.0,
        )
        
        assert entry.serial_no == 1
        assert entry.entity_name == "NVIDIA Corporation"
        assert entry.country_code == "2"
        assert entry.country_name == "United States of America"
    
    def test_entry_to_dict(self):
        """Test converting entry to dictionary."""
        entry = ForeignAssetEntry(
            serial_no=1,
            entity_name="Test Corp",
            initial_value_inr=100000.0,
            peak_value_inr=150000.0,
            closing_value_inr=120000.0,
        )
        
        result = entry.to_dict()
        
        assert 'serial_no' in result
        assert 'country' in result
        assert result['initial_value_inr'] == 100000.0


class TestForeignCustodialAccount:
    """Tests for ForeignCustodialAccount."""
    
    def test_account_creation(self):
        """Test creating a custodial account."""
        account = ForeignCustodialAccount(
            serial_no=1,
            institution_name="Charles Schwab",
            institution_address="San Francisco, CA",
            zip_code="94105",
            account_number="XXX-XXX123",
            peak_balance_inr=5000000.0,
            closing_balance_inr=4500000.0,
        )
        
        assert account.institution_name == "Charles Schwab"
        assert account.status == "Owner"


class TestDividendEntry:
    """Tests for DividendEntry."""
    
    def test_dividend_creation(self):
        """Test creating a dividend entry."""
        dividend = DividendEntry(
            symbol="NVDA",
            date=datetime(2025, 3, 15),
            gross_amount_usd=100.0,
            tax_withheld_usd=25.0,
            exchange_rate=85.0,
            gross_amount_inr=8500.0,
            tax_withheld_inr=2125.0,
        )
        
        assert dividend.symbol == "NVDA"
        assert dividend.gross_amount_inr == 8500.0


class TestScheduleFAReport:
    """Tests for ScheduleFAReport."""
    
    def test_report_creation(self):
        """Test creating a report."""
        config = ScheduleFAConfig(2025)
        report = ScheduleFAReport(config=config)
        
        assert report.config.calendar_year == 2025
        assert len(report.equity_entries) == 0
        assert len(report.custodial_accounts) == 0
    
    def test_report_calculate_totals(self):
        """Test calculating report totals."""
        config = ScheduleFAConfig(2025)
        report = ScheduleFAReport(config=config)
        
        # Add entries
        report.equity_entries.append(ForeignAssetEntry(
            serial_no=1,
            initial_value_inr=100000.0,
            peak_value_inr=150000.0,
            closing_value_inr=120000.0,
            sale_proceeds_inr=0.0,
        ))
        report.equity_entries.append(ForeignAssetEntry(
            serial_no=2,
            initial_value_inr=200000.0,
            peak_value_inr=250000.0,
            closing_value_inr=0.0,
            sale_proceeds_inr=220000.0,
        ))
        
        report.calculate_totals()
        
        assert report.total_initial_value_inr == 300000.0
        assert report.total_peak_value_inr == 400000.0
        assert report.total_closing_value_inr == 120000.0
        assert report.total_sale_proceeds_inr == 220000.0
    
    def test_report_entry_count(self):
        """Test getting entry count."""
        config = ScheduleFAConfig(2025)
        report = ScheduleFAReport(config=config)
        
        assert report.get_entry_count() == 0
        
        report.equity_entries.append(ForeignAssetEntry(serial_no=1))
        report.equity_entries.append(ForeignAssetEntry(serial_no=2))
        
        assert report.get_entry_count() == 2


class TestStockDataCache:
    """Tests for StockDataCache."""
    
    def test_cache_initialization(self):
        """Test cache initializes correctly."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = StockDataCache(f.name)
            
            assert cache._data['metadata'] == {}
            assert cache._data['prices'] == {}
    
    def test_cache_metadata(self):
        """Test caching metadata."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = StockDataCache(f.name)
            
            metadata = {'name': 'Test Corp', 'address': 'USA'}
            cache.set_metadata('TEST', metadata)
            
            assert cache.get_metadata('TEST') == metadata
            assert cache.has_symbol('TEST')
            assert not cache.has_symbol('OTHER')
    
    def test_cache_prices(self):
        """Test caching prices."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = StockDataCache(f.name)
            
            cache.set_price('TEST', '2025-01-01', 100.0)
            cache.set_price('TEST', '2025-01-02', 105.0)
            
            assert cache.get_price('TEST', '2025-01-01') == 100.0
            assert cache.get_price('TEST', '2025-01-02') == 105.0
            assert cache.get_price('TEST', '2025-01-03') is None
    
    def test_cache_peak_prices(self):
        """Test caching peak prices."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache = StockDataCache(f.name)
            
            cache.set_peak_price('TEST', '20250101_20251231', 150.0, '2025-06-15')
            
            price, date = cache.get_peak_price('TEST', '20250101_20251231')
            assert price == 150.0
            assert date == '2025-06-15'
            
            price, date = cache.get_peak_price('TEST', 'other_period')
            assert price is None
    
    def test_cache_save_load(self):
        """Test saving and loading cache."""
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            cache_file = f.name
        
        # Create and save
        cache1 = StockDataCache(cache_file)
        cache1.set_metadata('TEST', {'name': 'Test'})
        cache1.set_price('TEST', '2025-01-01', 100.0)
        cache1.save_cache()
        
        # Load in new instance
        cache2 = StockDataCache(cache_file)
        
        assert cache2.get_metadata('TEST') == {'name': 'Test'}
        assert cache2.get_price('TEST', '2025-01-01') == 100.0


class TestExchangeRateHandler:
    """Tests for ExchangeRateHandler."""
    
    def test_handler_initialization(self):
        """Test handler initializes with rates."""
        rates = {'2025-01-01': 83.0, '2025-01-02': 83.5}
        handler = ExchangeRateHandler(rates)
        
        rate = handler.get_rate_for_date(datetime(2025, 1, 1))
        assert rate == 83.0
    
    def test_handler_fallback(self):
        """Test handler uses fallback for missing dates."""
        rates = {'2025-01-01': 83.0}
        handler = ExchangeRateHandler(rates)
        
        # Should find nearby rate
        rate = handler.get_rate_for_date(datetime(2025, 1, 2))
        assert rate == 83.0  # Falls back to Jan 1
    
    def test_handler_date_parsing(self):
        """Test handler parses different date formats."""
        rates = {'2025-03-15': 85.0}
        handler = ExchangeRateHandler(rates)
        
        rate = handler.get_rate('03/15/2025', '%m/%d/%Y')
        assert rate == 85.0


class TestForeignAssetsParser:
    """Tests for ForeignAssetsParser."""
    
    def test_parser_initialization(self):
        """Test parser initializes correctly."""
        parser = ForeignAssetsParser(2025)
        
        assert parser.calendar_year == 2025
        assert parser.cy_start == datetime(2025, 1, 1)
        assert parser.cy_end == datetime(2025, 12, 31)
    
    def test_parse_date_formats(self):
        """Test parsing different date formats."""
        parser = ForeignAssetsParser(2025)
        
        assert parser.parse_date('01/15/2025') == datetime(2025, 1, 15)
        assert parser.parse_date('2025-01-15') == datetime(2025, 1, 15)
    
    def test_parse_amount(self):
        """Test parsing monetary amounts."""
        parser = ForeignAssetsParser(2025)
        
        assert parser.parse_amount('$1,234.56') == 1234.56
        assert parser.parse_amount('1234.56') == 1234.56
        assert parser.parse_amount('') == 0.0
    
    def test_parse_eac_transactions(self):
        """Test parsing EAC transactions."""
        parser = ForeignAssetsParser(2025)
        
        content = {
            'Transactions': [
                {
                    'Action': 'Sale',
                    'Date': '03/15/2025',
                    'Symbol': 'NVDA',
                    'TransactionDetails': [
                        {
                            'Details': {
                                'Type': 'RS',
                                'Shares': '100',
                                'VestDate': '01/15/2023',
                                'VestFairMarketValue': '$150.00',
                                'SalePrice': '$200.00',
                                'GrossProceeds': '$20000.00',
                                'GrantId': 'G123'
                            }
                        }
                    ]
                }
            ]
        }
        
        result = parser.parse_eac_transactions(content)
        
        assert result['symbol'] == 'NVDA'
        assert len(result['sales']) == 1
        assert result['sales'][0]['type'] == 'RSU'
        assert result['sales'][0]['shares'] == 100
    
    def test_parse_dividends(self):
        """Test parsing dividend transactions with tax withholding."""
        parser = ForeignAssetsParser(2025)
        
        # Test EAC dividends with tax withholding (separate transactions on same date)
        content = {
            'Transactions': [
                {
                    'Action': 'Dividend',
                    'Date': '06/15/2025',
                    'Symbol': 'NVDA',
                    'Amount': '$50.00'
                },
                {
                    'Action': 'Tax Withholding',
                    'Date': '06/15/2025',
                    'Symbol': 'NVDA',
                    'Amount': '-$12.50'
                }
            ]
        }
        
        result = parser.parse_eac_transactions(content)
        
        assert len(result['dividends']) == 1
        assert result['dividends'][0]['gross'] == 50.0
        assert result['dividends'][0]['tax'] == 12.50
        assert result['dividends'][0]['source'] == 'Equity Awards'
    
    def test_parse_brokerage_dividends_with_nra(self):
        """Test parsing brokerage dividends with NRA withholding."""
        parser = ForeignAssetsParser(2025)
        
        content = {
            'BrokerageTransactions': [
                {
                    'Action': 'Qualified Dividend',
                    'Date': '06/15/2025',
                    'Symbol': 'NVDA',
                    'Description': 'NVIDIA CORP',
                    'Amount': '$25.00',
                    'Quantity': '',
                    'Price': ''
                },
                {
                    'Action': 'NRA Withholding',
                    'Date': '06/15/2025',
                    'Symbol': 'NVDA',
                    'Description': 'NVIDIA CORP',
                    'Amount': '-$6.25',
                    'Quantity': '',
                    'Price': ''
                },
                {
                    'Action': 'NRA Tax Adj',
                    'Date': '06/15/2025',
                    'Symbol': 'NVDA',
                    'Description': 'NVIDIA CORP',
                    'Amount': '-$0.50',
                    'Quantity': '',
                    'Price': ''
                }
            ]
        }
        
        result = parser.parse_brokerage_transactions(content)
        
        assert len(result['dividends']) == 1
        assert result['dividends'][0]['gross'] == 25.0
        assert result['dividends'][0]['tax'] == 6.75  # 6.25 + 0.50
        assert result['dividends'][0]['source'] == 'Brokerage'


class TestScheduleFAGenerator:
    """Tests for ScheduleFAGenerator."""
    
    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        config = ScheduleFAConfig(2025)
        rates = {'2025-01-01': 83.0}
        generator = ScheduleFAGenerator(config, exchange_rates=rates)
        
        assert generator.config.calendar_year == 2025
    
    def test_generator_load_data(self):
        """Test loading data into generator."""
        config = ScheduleFAConfig(2025)
        generator = ScheduleFAGenerator(config)
        
        eac_data = {'sales': [], 'tax_sales': [], 'dividends': [], 'symbol': 'NVDA'}
        brokerage_data = {'holdings': {}, 'transactions': [], 'dividends': []}
        held_shares = []
        
        generator.load_data(eac_data, brokerage_data, held_shares)
        
        assert generator.eac_data == eac_data
        assert generator.brokerage_data == brokerage_data
        assert generator.held_shares == held_shares
    
    @patch('capital_gains.schedule_fa.price_fetcher._get_yfinance', return_value=None)
    def test_generator_without_yfinance(self, mock_yf):
        """Test generator works without yfinance."""
        config = ScheduleFAConfig(2025)
        rates = {'2025-01-01': 83.0, '2025-12-31': 85.0}
        generator = ScheduleFAGenerator(config, exchange_rates=rates)
        
        # Should work with empty data
        generator.load_data({}, {}, [])
        report = generator.generate()
        
        assert isinstance(report, ScheduleFAReport)
        assert report.config.calendar_year == 2025


class TestScheduleFAIntegration:
    """Integration tests for Schedule FA generation."""
    
    def test_end_to_end_generation(self):
        """Test end-to-end report generation with mock data."""
        config = ScheduleFAConfig(2025)
        rates = {
            '2025-01-15': 83.0,
            '2025-03-15': 84.0,
            '2025-06-15': 85.0,
            '2025-12-31': 86.0,
        }
        
        generator = ScheduleFAGenerator(config, exchange_rates=rates)
        
        # Mock EAC data
        eac_data = {
            'symbol': 'TEST',
            'sales': [
                {
                    'type': 'RSU',
                    'symbol': 'TEST',
                    'vest_date': '01/15/2023',
                    'sale_date': '03/15/2025',
                    'grant_id': 'G123',
                    'shares': 10,
                    'fmv': 100.0,
                    'sale_price': 150.0,
                    'proceeds': 1500.0,
                }
            ],
            'tax_sales': [],
            'dividends': [
                {'symbol': 'TEST', 'date': '06/15/2025', 'gross': 50.0, 'source': 'EAC'}
            ],
        }
        
        # Mock price fetcher
        with patch.object(generator.price_fetcher, 'get_company_info') as mock_info:
            mock_info.return_value = ('Test Corp', 'USA', '00000')
            
            with patch.object(generator.price_fetcher, 'get_peak_price_for_period') as mock_peak:
                mock_peak.return_value = (160.0, datetime(2025, 3, 10))
                
                with patch.object(generator.price_fetcher, 'get_closing_price') as mock_close:
                    mock_close.return_value = 145.0
                    
                    generator.load_data(eac_data=eac_data)
                    report = generator.generate()
        
        # Verify report
        assert report.get_entry_count() == 1
        assert len(report.dividends) == 1
        assert report.dividends[0].gross_amount_usd == 50.0
    
    def test_report_with_held_shares(self):
        """Test report generation with held shares."""
        config = ScheduleFAConfig(2025)
        rates = {'2025-01-01': 83.0, '2025-12-31': 86.0}
        
        generator = ScheduleFAGenerator(config, exchange_rates=rates)
        
        held_shares = [
            {
                'type': 'RSU',
                'symbol': 'TEST',
                'date': '01/01/2024',
                'shares': 50,
                'cost': 100.0,
            }
        ]
        
        with patch.object(generator.price_fetcher, 'get_company_info') as mock_info:
            mock_info.return_value = ('Test Corp', 'USA', '00000')
            
            with patch.object(generator.price_fetcher, 'get_peak_price_for_period') as mock_peak:
                mock_peak.return_value = (120.0, datetime(2025, 6, 15))
                
                with patch.object(generator.price_fetcher, 'get_closing_price') as mock_close:
                    mock_close.return_value = 110.0
                    
                    generator.load_data(eac_data={'sales': [], 'tax_sales': [], 'dividends': [], 'symbol': 'TEST'}, held_shares=held_shares)
                    report = generator.generate()
        
        assert report.get_entry_count() == 1
        assert report.equity_entries[0].shares == 50
        assert report.equity_entries[0].closing_value_inr > 0

