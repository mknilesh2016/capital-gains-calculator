"""
Unit tests for utility functions.
"""

import pytest
from datetime import datetime

from capital_gains.utils import (
    parse_currency,
    parse_date,
    get_advance_tax_quarter,
    format_currency_inr,
    format_currency_usd,
    ADVANCE_TAX_QUARTERS,
)


class TestParseCurrency:
    """Tests for parse_currency function."""
    
    def test_simple_amount(self):
        """Test parsing simple dollar amount."""
        assert parse_currency("$123.45") == 123.45
    
    def test_amount_with_commas(self):
        """Test parsing amount with thousand separators."""
        assert parse_currency("$1,234.56") == 1234.56
        assert parse_currency("$12,345,678.90") == 12345678.90
    
    def test_negative_amount(self):
        """Test parsing negative amount."""
        assert parse_currency("-$100.00") == 100.0  # Removes negative sign
    
    def test_empty_string(self):
        """Test parsing empty string."""
        assert parse_currency("") == 0.0
        assert parse_currency("   ") == 0.0
    
    def test_none_value(self):
        """Test parsing None value."""
        assert parse_currency(None) == 0.0
    
    def test_without_dollar_sign(self):
        """Test parsing amount without dollar sign."""
        assert parse_currency("123.45") == 123.45


class TestParseDate:
    """Tests for parse_date function."""
    
    def test_us_format(self):
        """Test parsing US date format (MM/DD/YYYY)."""
        result = parse_date("12/31/2024")
        assert result == datetime(2024, 12, 31)
    
    def test_custom_format(self):
        """Test parsing with custom format."""
        result = parse_date("2024-12-31", "%Y-%m-%d")
        assert result == datetime(2024, 12, 31)
    
    def test_invalid_format(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError):
            parse_date("31-12-2024")  # Wrong format


class TestGetAdvanceTaxQuarter:
    """Tests for get_advance_tax_quarter function."""
    
    def test_q1_april(self):
        """Test Q1 date in April."""
        result = get_advance_tax_quarter(datetime(2025, 4, 15))
        assert result == "Upto 15 Jun"
    
    def test_q1_june_early(self):
        """Test Q1 date early June."""
        result = get_advance_tax_quarter(datetime(2025, 6, 10))
        assert result == "Upto 15 Jun"
    
    def test_q1_june_15(self):
        """Test Q1 date on June 15."""
        result = get_advance_tax_quarter(datetime(2025, 6, 15))
        assert result == "Upto 15 Jun"
    
    def test_q2_june_late(self):
        """Test Q2 date late June."""
        result = get_advance_tax_quarter(datetime(2025, 6, 20))
        assert result == "16 Jun-15 Sep"
    
    def test_q2_august(self):
        """Test Q2 date in August."""
        result = get_advance_tax_quarter(datetime(2025, 8, 15))
        assert result == "16 Jun-15 Sep"
    
    def test_q3_october(self):
        """Test Q3 date in October."""
        result = get_advance_tax_quarter(datetime(2025, 10, 15))
        assert result == "16 Sep-15 Dec"
    
    def test_q4_january(self):
        """Test Q4 date in January."""
        result = get_advance_tax_quarter(datetime(2026, 1, 15))
        assert result == "16 Dec-15 Mar"
    
    def test_q5_march_late(self):
        """Test Q5 date late March."""
        result = get_advance_tax_quarter(datetime(2026, 3, 20))
        assert result == "16 Mar-31 Mar"


class TestFormatCurrency:
    """Tests for currency formatting functions."""
    
    def test_format_inr_with_symbol(self):
        """Test INR formatting with symbol."""
        result = format_currency_inr(123456.78)
        assert result == "₹123,456.78"
    
    def test_format_inr_without_symbol(self):
        """Test INR formatting without symbol."""
        result = format_currency_inr(123456.78, include_symbol=False)
        assert result == "123,456.78"
    
    def test_format_usd_with_symbol(self):
        """Test USD formatting with symbol."""
        result = format_currency_usd(1234.56)
        assert result == "$1,234.56"
    
    def test_format_usd_without_symbol(self):
        """Test USD formatting without symbol."""
        result = format_currency_usd(1234.56, include_symbol=False)
        assert result == "1,234.56"


class TestAdvanceTaxQuartersConstant:
    """Tests for ADVANCE_TAX_QUARTERS constant."""
    
    def test_quarter_count(self):
        """Test that there are 5 quarters."""
        assert len(ADVANCE_TAX_QUARTERS) == 5
    
    def test_quarter_names(self):
        """Test quarter names are correct."""
        assert "Upto 15 Jun" in ADVANCE_TAX_QUARTERS
        assert "16 Jun-15 Sep" in ADVANCE_TAX_QUARTERS
        assert "16 Sep-15 Dec" in ADVANCE_TAX_QUARTERS
        assert "16 Dec-15 Mar" in ADVANCE_TAX_QUARTERS
        assert "16 Mar-31 Mar" in ADVANCE_TAX_QUARTERS

