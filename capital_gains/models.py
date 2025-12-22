"""
Data models for the Capital Gains Calculator.

This module contains dataclasses representing transactions, stock lots,
and other data structures used throughout the application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class StockType(Enum):
    """Types of stock transactions."""
    RS = "RS"       # Restricted Stock (RSU)
    ESPP = "ESPP"   # Employee Stock Purchase Plan
    TRADE = "TRADE" # Regular trade


class TransactionSource(Enum):
    """Source of the transaction."""
    EAC = "EAC"             # Equity Awards Center
    INDIVIDUAL = "Individual" # Individual Brokerage
    INDIAN = "Indian"       # Indian broker


@dataclass
class SaleTransaction:
    """
    Represents a single stock sale transaction.
    
    Attributes:
        sale_date: Date when the stock was sold
        acquisition_date: Date when the stock was acquired (vest date for RSU, purchase date for others)
        stock_type: Type of stock (RS, ESPP, or TRADE)
        symbol: Stock ticker symbol
        shares: Number of shares sold
        sale_price_usd: Sale price per share in USD
        acquisition_price_usd: Cost basis per share in USD
        gross_proceeds_usd: Total sale proceeds in USD
        grant_id: Grant ID for RSU/ESPP (optional)
        source: Source of transaction (EAC, Individual, etc.)
        fees_and_commissions_usd: Transaction fees in USD
        fees_and_commissions_inr: Transaction fees in INR (calculated)
        sale_price_inr: Sale price per share in INR (calculated)
        acquisition_price_inr: Cost basis per share in INR (calculated)
        sale_exchange_rate: USD-INR rate on sale date
        acquisition_exchange_rate: USD-INR rate on acquisition date
        capital_gain_usd: Computed capital gain in USD
        capital_gain_inr: Computed capital gain in INR
        holding_period_days: Days between acquisition and sale
        is_long_term: True if LTCG (>2 years for foreign stocks), False if STCG
    """
    sale_date: datetime
    acquisition_date: datetime
    stock_type: str
    symbol: str
    shares: float
    sale_price_usd: float
    acquisition_price_usd: float
    gross_proceeds_usd: float
    grant_id: Optional[str] = None
    source: str = "EAC"
    fees_and_commissions_usd: float = 0.0
    fees_and_commissions_inr: float = 0.0
    sale_price_inr: float = 0.0
    acquisition_price_inr: float = 0.0
    sale_exchange_rate: float = 0.0
    acquisition_exchange_rate: float = 0.0
    capital_gain_usd: float = 0.0
    capital_gain_inr: float = 0.0
    holding_period_days: int = 0
    is_long_term: bool = False

    def get_type_label(self) -> str:
        """Get human-readable label for stock type."""
        labels = {'RS': 'RSU', 'ESPP': 'ESPP', 'TRADE': 'Trade'}
        return labels.get(self.stock_type, self.stock_type)
    
    def get_holding_period_str(self) -> str:
        """Get formatted holding period string like '2y 3m'."""
        years = self.holding_period_days // 365
        months = (self.holding_period_days % 365) // 30
        return f"{years}y {months}m"
    
    @property
    def total_sale_inr(self) -> float:
        """Total sale value in INR."""
        return self.sale_price_inr * self.shares
    
    @property
    def total_acquisition_inr(self) -> float:
        """Total acquisition cost in INR."""
        return self.acquisition_price_inr * self.shares


@dataclass
class StockLot:
    """
    Represents a purchase lot for FIFO matching.
    
    Attributes:
        purchase_date: Date when the stock was purchased
        symbol: Stock ticker symbol
        quantity: Number of shares purchased
        price: Purchase price per share
        remaining: Shares remaining (not yet sold)
    """
    purchase_date: datetime
    symbol: str
    quantity: float
    price: float
    remaining: float = field(default=0.0, init=False)
    
    def __post_init__(self):
        self.remaining = self.quantity


@dataclass
class IndianGains:
    """
    Represents capital gains from Indian investments.
    
    Attributes:
        source: Source name (e.g., 'Indian Stocks', 'Indian Mutual Funds')
        ltcg: Long-term capital gains amount in INR
        stcg: Short-term capital gains amount in INR
        transactions: List of individual transactions
        charges: Dictionary of various charges (STT, brokerage, etc.)
        dividends: Dividend income in INR
    """
    source: str
    ltcg: float = 0.0
    stcg: float = 0.0
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    charges: Dict[str, float] = field(default_factory=dict)
    dividends: float = 0.0
    
    @property
    def total(self) -> float:
        """Total capital gains (LTCG + STCG)."""
        return self.ltcg + self.stcg
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            'source': self.source,
            'ltcg': self.ltcg,
            'stcg': self.stcg,
            'transactions': self.transactions,
            'charges': self.charges,
            'dividends': self.dividends,
        }


@dataclass
class TaxData:
    """
    Contains all tax-related calculation data.
    
    Attributes include gains from all sources, exemptions applied,
    taxable amounts, taxes calculated, and final liability.
    """
    # Gains by source
    schwab_ltcg: float = 0.0
    schwab_stcg: float = 0.0
    indian_ltcg: float = 0.0
    indian_stcg: float = 0.0
    
    # Totals
    total_ltcg: float = 0.0
    total_stcg: float = 0.0
    
    # Exemptions
    ltcg_rebate: float = 125000.0
    rebate_used: float = 0.0
    indian_ltcg_after_rebate: float = 0.0
    
    # Net amounts after set-off
    net_ltcg: float = 0.0
    net_stcg: float = 0.0
    
    # Set-off details for transparency
    # Gains and losses by source (before set-off)
    foreign_ltcg_gain: float = 0.0
    foreign_ltcg_loss: float = 0.0
    indian_ltcg_gain: float = 0.0
    indian_ltcg_loss: float = 0.0
    foreign_stcg_gain: float = 0.0
    foreign_stcg_loss: float = 0.0
    indian_stcg_gain: float = 0.0
    indian_stcg_loss: float = 0.0
    
    # Set-off amounts applied
    stcg_loss_vs_foreign_stcg: float = 0.0  # STCG loss set off against foreign STCG gain
    stcg_loss_vs_indian_stcg: float = 0.0   # STCG loss set off against Indian STCG gain
    stcg_loss_vs_ltcg: float = 0.0          # Remaining STCG loss set off against LTCG gain
    ltcg_loss_vs_ltcg: float = 0.0          # LTCG loss set off against LTCG gain
    
    # Taxable amounts by category
    foreign_ltcg_taxable: float = 0.0
    indian_ltcg_taxable: float = 0.0
    indian_stcg_taxable: float = 0.0
    foreign_stcg_taxable: float = 0.0
    
    # Taxes by category
    foreign_ltcg_tax: float = 0.0
    indian_ltcg_tax: float = 0.0
    indian_stcg_tax: float = 0.0
    foreign_stcg_tax: float = 0.0
    
    # Tax totals
    ltcg_tax: float = 0.0
    stcg_tax: float = 0.0
    total_tax: float = 0.0
    
    # Payments and liability
    taxes_paid: float = 0.0
    tax_liability: float = 0.0
    
    # Tax rates (for reference)
    indian_ltcg_rate: float = 0.1495
    foreign_ltcg_rate: float = 0.1495
    indian_stcg_rate: float = 0.2392
    foreign_stcg_rate: float = 0.39
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Excel export."""
        return {
            'schwab_ltcg': self.schwab_ltcg,
            'schwab_stcg': self.schwab_stcg,
            'indian_ltcg': self.indian_ltcg,
            'indian_stcg': self.indian_stcg,
            'total_ltcg': self.total_ltcg,
            'total_stcg': self.total_stcg,
            'ltcg_rebate': self.ltcg_rebate,
            'rebate_used': self.rebate_used,
            'indian_ltcg_after_rebate': self.indian_ltcg_after_rebate,
            'net_ltcg': self.net_ltcg,
            'net_stcg': self.net_stcg,
            'foreign_ltcg_taxable': self.foreign_ltcg_taxable,
            'indian_ltcg_taxable': self.indian_ltcg_taxable,
            'indian_stcg_taxable': self.indian_stcg_taxable,
            'foreign_stcg_taxable': self.foreign_stcg_taxable,
            'foreign_ltcg_tax': self.foreign_ltcg_tax,
            'indian_ltcg_tax': self.indian_ltcg_tax,
            'indian_stcg_tax': self.indian_stcg_tax,
            'foreign_stcg_tax': self.foreign_stcg_tax,
            'ltcg_tax': self.ltcg_tax,
            'stcg_tax': self.stcg_tax,
            'total_tax': self.total_tax,
            'taxes_paid': self.taxes_paid,
            'tax_liability': self.tax_liability,
            'indian_ltcg_rate': self.indian_ltcg_rate,
            'foreign_ltcg_rate': self.foreign_ltcg_rate,
            'indian_stcg_rate': self.indian_stcg_rate,
            'foreign_stcg_rate': self.foreign_stcg_rate,
            # Set-off details
            'foreign_ltcg_gain': self.foreign_ltcg_gain,
            'foreign_ltcg_loss': self.foreign_ltcg_loss,
            'indian_ltcg_gain': self.indian_ltcg_gain,
            'indian_ltcg_loss': self.indian_ltcg_loss,
            'foreign_stcg_gain': self.foreign_stcg_gain,
            'foreign_stcg_loss': self.foreign_stcg_loss,
            'indian_stcg_gain': self.indian_stcg_gain,
            'indian_stcg_loss': self.indian_stcg_loss,
            'stcg_loss_vs_foreign_stcg': self.stcg_loss_vs_foreign_stcg,
            'stcg_loss_vs_indian_stcg': self.stcg_loss_vs_indian_stcg,
            'stcg_loss_vs_ltcg': self.stcg_loss_vs_ltcg,
            'ltcg_loss_vs_ltcg': self.ltcg_loss_vs_ltcg,
        }


@dataclass
class QuarterlyData:
    """Capital gains data for a single advance tax quarter."""
    ltcg: float = 0.0
    stcg: float = 0.0
    
    @property
    def total(self) -> float:
        return self.ltcg + self.stcg

