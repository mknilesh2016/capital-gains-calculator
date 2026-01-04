"""
Data models for Schedule FA (Foreign Assets) reporting.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any


@dataclass
class ScheduleFAConfig:
    """Configuration for Schedule FA generation."""
    calendar_year: int
    cache_file: str = "stock_cache.json"
    
    @property
    def assessment_year(self) -> str:
        """Assessment year string (e.g., '2026-27' for CY 2025)."""
        return f"{self.calendar_year + 1}-{str(self.calendar_year + 2)[2:]}"
    
    @property
    def cy_start(self) -> datetime:
        """Calendar year start date."""
        return datetime(self.calendar_year, 1, 1)
    
    @property
    def cy_end(self) -> datetime:
        """Calendar year end date."""
        return datetime(self.calendar_year, 12, 31)
    
    @property
    def fy_start(self) -> datetime:
        """Financial year start date."""
        return datetime(self.calendar_year, 4, 1)
    
    @property
    def fy_end(self) -> datetime:
        """Financial year end date."""
        return datetime(self.calendar_year + 1, 3, 31)


@dataclass
class ForeignAssetEntry:
    """
    Represents a single entry in Schedule FA Section A3.
    (Details of Foreign Equity and Debt Interest)
    """
    serial_no: int = 0
    country_code: str = "2"  # USA
    country_name: str = "United States of America"
    entity_name: str = ""
    entity_address: str = ""
    zip_code: str = ""
    nature_of_entity: str = ""  # RSU, ESPP, Stock, ETF, etc.
    
    # Dates
    acquisition_date: Optional[datetime] = None
    sale_date: Optional[datetime] = None
    
    # Values in USD
    shares: float = 0.0
    cost_per_share_usd: float = 0.0
    peak_price_usd: float = 0.0
    closing_price_usd: float = 0.0
    sale_price_usd: float = 0.0
    
    # Exchange rates
    rate_at_acquisition: float = 0.0
    rate_at_peak: float = 0.0
    rate_at_close: float = 0.0
    rate_at_sale: float = 0.0
    
    # Values in INR (calculated)
    initial_value_inr: float = 0.0
    peak_value_inr: float = 0.0
    closing_value_inr: float = 0.0
    sale_proceeds_inr: float = 0.0
    dividend_income_inr: float = 0.0
    
    # Peak date
    peak_date: Optional[datetime] = None
    
    # Source tracking
    source: str = ""  # EAC, Brokerage, etc.
    grant_id: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'serial_no': self.serial_no,
            'country': f"{self.country_code}-{self.country_name}",
            'entity_name': self.entity_name,
            'entity_address': self.entity_address,
            'zip_code': self.zip_code,
            'nature': self.nature_of_entity,
            'acquisition_date': self.acquisition_date,
            'sale_date': self.sale_date,
            'shares': self.shares,
            'cost_per_share_usd': self.cost_per_share_usd,
            'initial_value_inr': self.initial_value_inr,
            'peak_value_inr': self.peak_value_inr,
            'closing_value_inr': self.closing_value_inr,
            'sale_proceeds_inr': self.sale_proceeds_inr,
            'dividend_income_inr': self.dividend_income_inr,
        }


@dataclass
class ForeignCustodialAccount:
    """
    Represents a foreign custodial/depository account (Section A1).
    """
    serial_no: int = 0
    country_code: str = "2"
    country_name: str = "United States of America"
    institution_name: str = ""
    institution_address: str = ""
    zip_code: str = ""
    account_number: str = ""
    status: str = "Owner"  # Owner, Beneficial Owner, etc.
    opening_date: Optional[datetime] = None
    
    peak_balance_inr: float = 0.0
    closing_balance_inr: float = 0.0
    interest_earned_inr: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'serial_no': self.serial_no,
            'country': f"{self.country_code}-{self.country_name}",
            'institution_name': self.institution_name,
            'institution_address': self.institution_address,
            'zip_code': self.zip_code,
            'account_number': self.account_number,
            'status': self.status,
            'opening_date': self.opening_date,
            'peak_balance_inr': self.peak_balance_inr,
            'closing_balance_inr': self.closing_balance_inr,
            'interest_earned_inr': self.interest_earned_inr,
        }


@dataclass
class DividendEntry:
    """Represents dividend income from foreign sources (for Schedule FSI)."""
    symbol: str = ""
    date: Optional[datetime] = None
    gross_amount_usd: float = 0.0
    tax_withheld_usd: float = 0.0
    exchange_rate: float = 0.0
    gross_amount_inr: float = 0.0
    tax_withheld_inr: float = 0.0
    source: str = ""  # EAC, Brokerage


@dataclass
class ScheduleFAReport:
    """
    Complete Schedule FA report data.
    """
    config: ScheduleFAConfig
    
    # Section A3 - Foreign Equity and Debt Interest
    equity_entries: List[ForeignAssetEntry] = field(default_factory=list)
    
    # Section A1 - Foreign Custodial Accounts
    custodial_accounts: List[ForeignCustodialAccount] = field(default_factory=list)
    
    # Dividends (for Schedule FSI)
    dividends: List[DividendEntry] = field(default_factory=list)
    
    # Summary totals
    total_initial_value_inr: float = 0.0
    total_peak_value_inr: float = 0.0
    total_closing_value_inr: float = 0.0
    total_sale_proceeds_inr: float = 0.0
    total_dividend_inr: float = 0.0
    total_dividend_tax_inr: float = 0.0
    
    # Breakdown by category
    regular_sales_total_inr: float = 0.0
    tax_sales_total_inr: float = 0.0
    held_shares_closing_inr: float = 0.0
    brokerage_closing_inr: float = 0.0
    
    def calculate_totals(self):
        """Calculate summary totals from entries."""
        self.total_initial_value_inr = sum(e.initial_value_inr for e in self.equity_entries)
        self.total_peak_value_inr = sum(e.peak_value_inr for e in self.equity_entries)
        self.total_closing_value_inr = sum(e.closing_value_inr for e in self.equity_entries)
        self.total_sale_proceeds_inr = sum(e.sale_proceeds_inr for e in self.equity_entries)
        self.total_dividend_inr = sum(d.gross_amount_inr for d in self.dividends)
        self.total_dividend_tax_inr = sum(d.tax_withheld_inr for d in self.dividends)
    
    def get_entry_count(self) -> int:
        """Get total number of equity entries."""
        return len(self.equity_entries)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for export."""
        return {
            'assessment_year': self.config.assessment_year,
            'calendar_year': self.config.calendar_year,
            'entry_count': self.get_entry_count(),
            'total_initial_value_inr': self.total_initial_value_inr,
            'total_peak_value_inr': self.total_peak_value_inr,
            'total_closing_value_inr': self.total_closing_value_inr,
            'total_sale_proceeds_inr': self.total_sale_proceeds_inr,
            'total_dividend_inr': self.total_dividend_inr,
        }

