"""
Schedule FA Report Generator.
Generates Schedule FA (Foreign Assets) reports for Indian Income Tax Returns.
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

from .models import (
    ScheduleFAConfig, 
    ForeignAssetEntry, 
    ForeignCustodialAccount,
    DividendEntry,
    ScheduleFAReport,
)
from .stock_cache import StockDataCache
from .price_fetcher import StockPriceFetcher


class ExchangeRateHandler:
    """Handles exchange rate lookups."""
    
    def __init__(self, rates: Dict[str, float] = None):
        self._rates = rates or {}
        self._last_rate = 85.0  # Default fallback
    
    def get_rate(self, date_str: str, format: str = '%m/%d/%Y') -> float:
        """Get exchange rate for a date string."""
        try:
            dt = datetime.strptime(date_str, format)
            return self.get_rate_for_date(dt)
        except ValueError:
            # Try alternative formats
            for fmt in ['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return self.get_rate_for_date(dt)
                except ValueError:
                    continue
            return self._last_rate
    
    def get_rate_for_date(self, dt: datetime) -> float:
        """Get exchange rate for a datetime."""
        key = dt.strftime('%Y-%m-%d')
        
        if key in self._rates:
            self._last_rate = self._rates[key]
            return self._rates[key]
        
        # Try to find closest available rate
        for days_back in range(1, 10):
            for delta in [days_back, -days_back]:
                try:
                    check_key = (dt - timedelta(days=delta)).strftime('%Y-%m-%d')
                    if check_key in self._rates:
                        self._last_rate = self._rates[check_key]
                        return self._rates[check_key]
                except:
                    pass
        
        return self._last_rate


from datetime import timedelta


class ScheduleFAGenerator:
    """
    Generates Schedule FA reports from parsed foreign assets data.
    """
    
    def __init__(
        self, 
        config: ScheduleFAConfig,
        exchange_rates: Dict[str, float] = None,
        cache_file: str = None
    ):
        self.config = config
        self.cache = StockDataCache(cache_file or config.cache_file)
        self.price_fetcher = StockPriceFetcher(config, self.cache)
        self.exchange_handler = ExchangeRateHandler(exchange_rates)
        
        # Data storage
        self.eac_data: Dict[str, Any] = {}
        self.brokerage_data: Dict[str, Any] = {}
        self.held_shares: List[Dict] = []
        
    def load_data(
        self,
        eac_data: Dict[str, Any] = None,
        brokerage_data: Dict[str, Any] = None,
        held_shares: List[Dict] = None
    ):
        """Load parsed data into the generator."""
        self.eac_data = eac_data or {}
        self.brokerage_data = brokerage_data or {}
        self.held_shares = held_shares or []
    
    def prefetch_prices(self) -> Dict[str, bool]:
        """
        Prefetch prices for all symbols.
        Returns dict of {symbol: was_cached}
        """
        symbols = set()
        
        # From EAC data
        if self.eac_data:
            symbols.add(self.eac_data.get('symbol', 'NVDA'))
        
        # From brokerage data
        if self.brokerage_data:
            for sym in self.brokerage_data.get('holdings', {}).keys():
                symbols.add(sym)
        
        return self.price_fetcher.prefetch_symbols(symbols)
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string to datetime."""
        formats = ['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not parse date: {date_str}")
    
    def generate(self) -> ScheduleFAReport:
        """
        Generate complete Schedule FA report.
        """
        report = ScheduleFAReport(config=self.config)
        serial_no = 0
        
        symbol = self.eac_data.get('symbol', 'NVDA')
        company_name, company_addr, company_zip = self.price_fetcher.get_company_info(symbol)
        
        # ===== Process Regular Sales =====
        sales = self.eac_data.get('sales', [])
        for sale in sales:
            serial_no += 1
            entry = self._create_sale_entry(sale, serial_no, company_name, company_addr, company_zip)
            report.equity_entries.append(entry)
            report.regular_sales_total_inr += entry.sale_proceeds_inr
        
        # ===== Process Tax Withholding Sales =====
        tax_sales = self.eac_data.get('tax_sales', [])
        for tax_sale in tax_sales:
            serial_no += 1
            entry = self._create_tax_sale_entry(tax_sale, serial_no, company_name, company_addr, company_zip)
            report.equity_entries.append(entry)
            report.tax_sales_total_inr += entry.sale_proceeds_inr
        
        # ===== Process Held Shares =====
        close_price = self.price_fetcher.get_closing_price(symbol)
        rate_close = self.exchange_handler.get_rate_for_date(self.config.cy_end)
        
        for held in self.held_shares:
            serial_no += 1
            entry = self._create_held_entry(
                held, serial_no, company_name, company_addr, company_zip,
                close_price, rate_close
            )
            report.equity_entries.append(entry)
            report.held_shares_closing_inr += entry.closing_value_inr
        
        # ===== Process Brokerage Holdings (aggregated by symbol) =====
        holdings = self.brokerage_data.get('holdings', {})
        transactions = self.brokerage_data.get('transactions', [])
        
        for sym, holding in holdings.items():
            if not holding.get('symbol'):
                continue
            
            # Skip if no meaningful activity
            total_shares = holding.get('shares', 0)
            shares_sold = holding.get('shares_sold', 0)
            if total_shares == 0 and shares_sold == 0:
                continue
            
            serial_no += 1
            entry = self._create_brokerage_holding_entry(
                sym, holding, transactions, serial_no
            )
            if entry:
                report.equity_entries.append(entry)
                report.brokerage_closing_inr += entry.closing_value_inr
                if entry.sale_proceeds_inr > 0:
                    report.brokerage_closing_inr += entry.sale_proceeds_inr
        
        # ===== Process Dividends =====
        all_dividends = []
        all_dividends.extend(self.eac_data.get('dividends', []))
        all_dividends.extend(self.brokerage_data.get('dividends', []))
        
        for div in all_dividends:
            rate = self.exchange_handler.get_rate(div['date'])
            dividend_entry = DividendEntry(
                symbol=div['symbol'],
                date=self._parse_date(div['date']),
                gross_amount_usd=div['gross'],
                tax_withheld_usd=div.get('tax', 0),
                exchange_rate=rate,
                gross_amount_inr=div['gross'] * rate,
                tax_withheld_inr=div.get('tax', 0) * rate,
                source=div.get('source', ''),
            )
            report.dividends.append(dividend_entry)
        
        # ===== Allocate Dividends to Holdings =====
        self._allocate_dividends_to_entries(report)
        
        # ===== Create Custodial Accounts =====
        if self.eac_data or self.held_shares:
            account = ForeignCustodialAccount(
                serial_no=1,
                institution_name="Charles Schwab",
                institution_address="San Francisco, CA",
                zip_code="94105",
                account_number="XXX-XXX790",
                status="Owner",
                peak_balance_inr=report.held_shares_closing_inr + report.regular_sales_total_inr,
                closing_balance_inr=report.held_shares_closing_inr,
            )
            report.custodial_accounts.append(account)
        
        if self.brokerage_data:
            account = ForeignCustodialAccount(
                serial_no=2,
                institution_name="Charles Schwab",
                institution_address="San Francisco, CA",
                zip_code="94105",
                account_number="XXX-XXX256",
                status="Owner",
                peak_balance_inr=report.brokerage_closing_inr,
                closing_balance_inr=report.brokerage_closing_inr,
            )
            report.custodial_accounts.append(account)
        
        # Calculate totals
        report.calculate_totals()
        
        # Save cache
        self.cache.save_cache()
        
        return report
    
    def _create_sale_entry(
        self, 
        sale: Dict, 
        serial_no: int,
        company_name: str,
        company_addr: str,
        company_zip: str
    ) -> ForeignAssetEntry:
        """Create a ForeignAssetEntry for a regular sale."""
        vest_date = self._parse_date(sale['vest_date'])
        sale_date = self._parse_date(sale['sale_date'])
        
        rate_vest = self.exchange_handler.get_rate(sale['vest_date'])
        rate_sale = self.exchange_handler.get_rate(sale['sale_date'])
        
        # Calculate peak for holding period
        peak_start = max(vest_date, self.config.cy_start)
        peak_price, peak_dt = self.price_fetcher.get_peak_price_for_period(
            sale['symbol'], peak_start, sale_date
        )
        rate_peak = self.exchange_handler.get_rate_for_date(peak_dt)
        
        cost_usd = sale['shares'] * sale['fmv']
        initial_inr = cost_usd * rate_vest
        peak_inr = sale['shares'] * peak_price * rate_peak
        proceeds_inr = sale['proceeds'] * rate_sale
        
        return ForeignAssetEntry(
            serial_no=serial_no,
            entity_name=company_name,
            entity_address=company_addr,
            zip_code=company_zip,
            nature_of_entity=sale['type'],
            acquisition_date=vest_date,
            sale_date=sale_date,
            shares=sale['shares'],
            cost_per_share_usd=sale['fmv'],
            peak_price_usd=peak_price,
            sale_price_usd=sale.get('sale_price', 0),
            rate_at_acquisition=rate_vest,
            rate_at_peak=rate_peak,
            rate_at_sale=rate_sale,
            initial_value_inr=initial_inr,
            peak_value_inr=peak_inr,
            closing_value_inr=0,  # Sold
            sale_proceeds_inr=proceeds_inr,
            peak_date=peak_dt,
            source='EAC',
            grant_id=sale.get('grant_id', ''),
        )
    
    def _create_tax_sale_entry(
        self,
        tax_sale: Dict,
        serial_no: int,
        company_name: str,
        company_addr: str,
        company_zip: str
    ) -> ForeignAssetEntry:
        """Create a ForeignAssetEntry for a tax withholding sale."""
        txn_date = self._parse_date(tax_sale['date'])
        rate = self.exchange_handler.get_rate(tax_sale['date'])
        
        value_usd = tax_sale['shares'] * tax_sale['fmv']
        value_inr = value_usd * rate
        
        return ForeignAssetEntry(
            serial_no=serial_no,
            entity_name=company_name,
            entity_address=company_addr,
            zip_code=company_zip,
            nature_of_entity=tax_sale['type'],
            acquisition_date=txn_date,
            sale_date=txn_date,  # Same-day sale
            shares=tax_sale['shares'],
            cost_per_share_usd=tax_sale['fmv'],
            peak_price_usd=tax_sale['fmv'],  # Peak = FMV for same-day
            sale_price_usd=tax_sale['fmv'],
            rate_at_acquisition=rate,
            rate_at_peak=rate,
            rate_at_sale=rate,
            initial_value_inr=value_inr,
            peak_value_inr=value_inr,
            closing_value_inr=0,  # Sold
            sale_proceeds_inr=value_inr,
            peak_date=txn_date,
            source='EAC',
            grant_id=tax_sale.get('grant_id', ''),
        )
    
    def _create_held_entry(
        self,
        held: Dict,
        serial_no: int,
        company_name: str,
        company_addr: str,
        company_zip: str,
        close_price: float,
        rate_close: float
    ) -> ForeignAssetEntry:
        """Create a ForeignAssetEntry for held shares."""
        acq_date = self._parse_date(held['date'])
        rate_acq = self.exchange_handler.get_rate(held['date'])
        
        # Calculate peak for holding period
        peak_start = max(acq_date, self.config.cy_start)
        peak_price, peak_dt = self.price_fetcher.get_peak_price_for_period(
            held['symbol'], peak_start, self.config.cy_end
        )
        rate_peak = self.exchange_handler.get_rate_for_date(peak_dt)
        
        initial_inr = held['shares'] * held['cost'] * rate_acq
        peak_inr = held['shares'] * peak_price * rate_peak
        close_inr = held['shares'] * close_price * rate_close
        
        return ForeignAssetEntry(
            serial_no=serial_no,
            entity_name=company_name,
            entity_address=company_addr,
            zip_code=company_zip,
            nature_of_entity=held['type'],
            acquisition_date=acq_date,
            shares=held['shares'],
            cost_per_share_usd=held['cost'],
            peak_price_usd=peak_price,
            closing_price_usd=close_price,
            rate_at_acquisition=rate_acq,
            rate_at_peak=rate_peak,
            rate_at_close=rate_close,
            initial_value_inr=initial_inr,
            peak_value_inr=peak_inr,
            closing_value_inr=close_inr,
            peak_date=peak_dt,
            source='EAC',
        )
    
    def _create_brokerage_holding_entry(
        self,
        symbol: str,
        holding: Dict,
        transactions: List[Dict],
        serial_no: int
    ) -> Optional[ForeignAssetEntry]:
        """
        Create a ForeignAssetEntry for a brokerage holding (aggregated by symbol).
        
        Schedule FA requires one entry per holding showing:
        - Initial value (total cost basis)
        - Peak value during the year
        - Closing value (shares remaining at year end)
        - Sale proceeds (if any shares sold)
        """
        company_name, company_addr, company_zip = self.price_fetcher.get_company_info(symbol)
        
        # Get transactions for this symbol
        sym_txns = [t for t in transactions if t['symbol'] == symbol]
        if not sym_txns:
            return None
        
        # Find first acquisition date
        buy_txns = [t for t in sym_txns if t['action'] in ['Buy', 'Reinvest']]
        sell_txns = [t for t in sym_txns if t['action'] == 'Sell']
        
        if buy_txns:
            first_buy = min(buy_txns, key=lambda t: self._parse_date(t['date']))
            first_acq_date = self._parse_date(first_buy['date'])
        else:
            # Selling shares acquired before this year
            first_acq_date = self.config.cy_start
        
        # Calculate total cost basis (initial value)
        total_cost_usd = holding.get('cost_basis', 0)
        rate_acq = self.exchange_handler.get_rate_for_date(first_acq_date)
        initial_inr = total_cost_usd * rate_acq
        
        # Calculate sale proceeds
        total_proceeds_usd = holding.get('sales_proceeds', 0)
        sale_date = None
        rate_sale = 0
        proceeds_inr = 0
        
        if sell_txns and total_proceeds_usd > 0:
            # Use last sale date
            last_sale = max(sell_txns, key=lambda t: self._parse_date(t['date']))
            sale_date = self._parse_date(last_sale['date'])
            rate_sale = self.exchange_handler.get_rate_for_date(sale_date)
            proceeds_inr = total_proceeds_usd * rate_sale
        
        # Calculate peak value
        shares_held = holding.get('shares', 0)
        shares_bought = sum(t['shares'] for t in buy_txns) if buy_txns else 0
        max_shares = max(shares_held, shares_bought)
        
        try:
            peak_price, peak_dt = self.price_fetcher.get_peak_price_for_period(
                symbol, first_acq_date, self.config.cy_end
            )
            rate_peak = self.exchange_handler.get_rate_for_date(peak_dt)
            close_price = self.price_fetcher.get_closing_price(symbol)
            rate_close = self.exchange_handler.get_rate_for_date(self.config.cy_end)
        except Exception:
            # Fallback to cost basis prices
            avg_price = total_cost_usd / shares_bought if shares_bought > 0 else 0
            peak_price = close_price = avg_price
            rate_peak = rate_close = rate_acq
            peak_dt = first_acq_date
        
        peak_inr = max_shares * peak_price * rate_peak
        
        # Closing value (shares still held at year end)
        if shares_held > 0:
            close_inr = shares_held * close_price * rate_close
        else:
            close_inr = 0
        
        # Determine nature (ETF, Stock, etc. based on description)
        desc = holding.get('description', symbol)
        if 'ETF' in desc.upper():
            nature = 'ETF'
        elif 'CORP' in desc.upper() or 'INC' in desc.upper():
            nature = 'Stock'
        else:
            nature = 'Stock'
        
        return ForeignAssetEntry(
            serial_no=serial_no,
            entity_name=company_name,
            entity_address=company_addr,
            zip_code=company_zip,
            nature_of_entity=nature,
            acquisition_date=first_acq_date,
            sale_date=sale_date,
            shares=shares_held if shares_held > 0 else holding.get('shares_sold', 0),
            cost_per_share_usd=total_cost_usd / shares_bought if shares_bought > 0 else 0,
            peak_price_usd=peak_price,
            closing_price_usd=close_price if shares_held > 0 else 0,
            rate_at_acquisition=rate_acq,
            rate_at_peak=rate_peak,
            rate_at_close=rate_close if shares_held > 0 else 0,
            rate_at_sale=rate_sale,
            initial_value_inr=initial_inr,
            peak_value_inr=peak_inr,
            closing_value_inr=close_inr,
            sale_proceeds_inr=proceeds_inr,
            peak_date=peak_dt,
            source='Brokerage',
        )
    
    def _allocate_dividends_to_entries(self, report: ScheduleFAReport) -> None:
        """
        Allocate dividends to equity entries proportionally based on shares held.
        
        For each dividend payment, distributes the dividend amount to entries
        that were held on that date, proportional to their share count.
        """
        for div in report.dividends:
            if not div.date:
                continue
            
            # Find all entries held on dividend date
            eligible_entries = []
            total_shares = 0.0
            
            for entry in report.equity_entries:
                # Entry must be acquired before or on dividend date
                if entry.acquisition_date and entry.acquisition_date <= div.date:
                    # If sold, must not be sold before dividend date
                    if entry.sale_date is None or entry.sale_date > div.date:
                        eligible_entries.append(entry)
                        total_shares += entry.shares
            
            # Allocate dividend proportionally to eligible entries
            if total_shares > 0 and eligible_entries:
                for entry in eligible_entries:
                    share_fraction = entry.shares / total_shares
                    entry.dividend_income_inr += div.gross_amount_inr * share_fraction

