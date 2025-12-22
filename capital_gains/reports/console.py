"""
Console reporting module for capital gains.

This module provides the ConsoleReporter class for generating
formatted text reports to the console.
"""

from typing import List, Dict

from ..models import SaleTransaction, IndianGains, QuarterlyData
from ..utils import get_advance_tax_quarter, ADVANCE_TAX_QUARTERS


class ConsoleReporter:
    """
    Reporter for generating console output.
    
    Provides methods for printing detailed transaction reports,
    summaries, and quarterly breakdowns.
    """
    
    def print_detailed_report(
        self,
        transactions: List[SaleTransaction],
        title: str = "DETAILED CAPITAL GAINS REPORT"
    ) -> None:
        """
        Print detailed transaction-wise report.
        
        Args:
            transactions: List of sale transactions
            title: Report title
        """
        print("\n" + "=" * 120)
        print(title)
        print("=" * 120)
        
        # Sort by sale date
        sorted_txns = sorted(
            transactions,
            key=lambda x: (x.sale_date, x.stock_type, x.symbol)
        )
        
        for i, txn in enumerate(sorted_txns, 1):
            self._print_transaction(i, txn)
    
    def _print_transaction(self, index: int, txn: SaleTransaction) -> None:
        """Print a single transaction."""
        type_label = txn.get_type_label()
        
        print(f"\n{'─' * 120}")
        print(f"Transaction #{index} [{txn.source}]")
        print(f"{'─' * 120}")
        print(f"  Sale Date:           {txn.sale_date.strftime('%d-%b-%Y')}")
        print(f"  Acquisition Date:    {txn.acquisition_date.strftime('%d-%b-%Y')}")
        print(f"  Stock Type:          {txn.stock_type} ({type_label})")
        print(f"  Symbol:              {txn.symbol}")
        
        shares_str = f"{txn.shares:.3f}" if txn.shares != int(txn.shares) else str(int(txn.shares))
        print(f"  Shares Sold:         {shares_str}")
        print(f"  Grant ID:            {txn.grant_id or 'N/A'}")
        print(f"  Holding Period:      {txn.holding_period_days} days ({txn.get_holding_period_str()})")
        print(f"  Classification:      {'LONG TERM' if txn.is_long_term else 'SHORT TERM'}")
        print()
        
        # Value table
        print(f"  ┌{'─' * 50}┬{'─' * 25}┬{'─' * 25}┐")
        print(f"  │{'':^50}│{'USD':^25}│{'INR':^25}│")
        print(f"  ├{'─' * 50}┼{'─' * 25}┼{'─' * 25}┤")
        print(f"  │ Sale Price (per share)                          │ ${txn.sale_price_usd:>22.4f} │ ₹{txn.sale_price_inr:>22.2f} │")
        print(f"  │ Acquisition Price (per share)                   │ ${txn.acquisition_price_usd:>22.4f} │ ₹{txn.acquisition_price_inr:>22.2f} │")
        print(f"  │ Exchange Rate (Sale Date)                       │{'':>25}│ {txn.sale_exchange_rate:>24.2f} │")
        print(f"  │ Exchange Rate (Acquisition Date)                │{'':>25}│ {txn.acquisition_exchange_rate:>24.2f} │")
        print(f"  ├{'─' * 50}┼{'─' * 25}┼{'─' * 25}┤")
        
        total_sale = txn.sale_price_usd * txn.shares
        total_acq = txn.acquisition_price_usd * txn.shares
        print(f"  │ Total Sale Value ({shares_str} shares)                       │ ${total_sale:>22.2f} │ ₹{txn.total_sale_inr:>22.2f} │"[:107] + "│")
        print(f"  │ Total Acquisition Cost ({shares_str} shares)                 │ ${total_acq:>22.2f} │ ₹{txn.total_acquisition_inr:>22.2f} │"[:107] + "│")
        print(f"  ├{'─' * 50}┼{'─' * 25}┼{'─' * 25}┤")
        print(f"  │ CAPITAL GAIN                                    │ ${txn.capital_gain_usd:>22.2f} │ ₹{txn.capital_gain_inr:>22.2f} │")
        print(f"  └{'─' * 50}┴{'─' * 25}┴{'─' * 25}┘")
    
    def print_summary_report(
        self,
        transactions: List[SaleTransaction],
        title: str = "CAPITAL GAINS SUMMARY"
    ) -> None:
        """
        Print summary report with totals and breakdowns.
        
        Args:
            transactions: List of sale transactions
            title: Report title
        """
        # Categorize transactions
        long_term = [t for t in transactions if t.is_long_term]
        short_term = [t for t in transactions if not t.is_long_term]
        eac_txns = [t for t in transactions if t.source == "EAC"]
        individual_txns = [t for t in transactions if t.source == "Individual"]
        rsu_txns = [t for t in transactions if t.stock_type == "RS"]
        espp_txns = [t for t in transactions if t.stock_type == "ESPP"]
        trade_txns = [t for t in transactions if t.stock_type == "TRADE"]
        
        # Calculate totals
        total_long_term_inr = sum(t.capital_gain_inr for t in long_term)
        total_short_term_inr = sum(t.capital_gain_inr for t in short_term)
        total_long_term_usd = sum(t.capital_gain_usd for t in long_term)
        total_short_term_usd = sum(t.capital_gain_usd for t in short_term)
        total_sale_inr = sum(t.total_sale_inr for t in transactions)
        total_acquisition_inr = sum(t.total_acquisition_inr for t in transactions)
        
        print("\n")
        print("╔" + "═" * 118 + "╗")
        print("║" + f" {title} ".center(118) + "║")
        print("╠" + "═" * 118 + "╣")
        
        # Overview
        print("║" + " TRANSACTION OVERVIEW ".ljust(118) + "║")
        print("╟" + "─" * 118 + "╢")
        print(f"║   Total Transactions:         {len(transactions):>10}".ljust(119) + "║")
        print(f"║   - EAC (RSU/ESPP):           {len(eac_txns):>10}".ljust(119) + "║")
        print(f"║   - Individual (Trades):      {len(individual_txns):>10}".ljust(119) + "║")
        print(f"║   Total Shares Sold:          {sum(t.shares for t in transactions):>10.2f}".ljust(119) + "║")
        print("║".ljust(119) + "║")
        print(f"║   Total Sale Value (INR):     ₹{total_sale_inr:>20,.2f}".ljust(119) + "║")
        print(f"║   Total Acquisition Cost:     ₹{total_acquisition_inr:>20,.2f}".ljust(119) + "║")
        
        print("╠" + "═" * 118 + "╣")
        print("║" + " CAPITAL GAINS CLASSIFICATION ".ljust(118) + "║")
        print("╟" + "─" * 118 + "╢")
        
        # Long Term
        print("║".ljust(119) + "║")
        print("║   📈 LONG TERM CAPITAL GAINS - FOREIGN STOCKS (Holding > 2 years)".ljust(119) + "║")
        print(f"║      Number of Transactions:  {len(long_term):>10}".ljust(119) + "║")
        print(f"║      Total Shares:            {sum(t.shares for t in long_term):>10.2f}".ljust(119) + "║")
        print(f"║      Capital Gain (USD):      ${total_long_term_usd:>20,.2f}".ljust(119) + "║")
        print(f"║      Capital Gain (INR):      ₹{total_long_term_inr:>20,.2f}".ljust(119) + "║")
        
        # Short Term
        print("║".ljust(119) + "║")
        print("║   📉 SHORT TERM CAPITAL GAINS - FOREIGN STOCKS (Holding ≤ 2 years)".ljust(119) + "║")
        print(f"║      Number of Transactions:  {len(short_term):>10}".ljust(119) + "║")
        print(f"║      Total Shares:            {sum(t.shares for t in short_term):>10.2f}".ljust(119) + "║")
        print(f"║      Capital Gain (USD):      ${total_short_term_usd:>20,.2f}".ljust(119) + "║")
        print(f"║      Capital Gain (INR):      ₹{total_short_term_inr:>20,.2f}".ljust(119) + "║")
        
        # Total
        print("╠" + "═" * 118 + "╣")
        print("║" + " TOTAL CAPITAL GAINS ".center(118) + "║")
        print("╟" + "─" * 118 + "╢")
        print(f"║      Total (USD):             ${(total_long_term_usd + total_short_term_usd):>20,.2f}".ljust(119) + "║")
        print(f"║      Total (INR):             ₹{(total_long_term_inr + total_short_term_inr):>20,.2f}".ljust(119) + "║")
        print("╚" + "═" * 118 + "╝")
        
        # Print breakdowns
        self._print_source_breakdown(eac_txns, individual_txns)
        self._print_type_breakdown(rsu_txns, espp_txns, trade_txns)
        self._print_symbol_breakdown(transactions)
    
    def _print_source_breakdown(self, eac_txns, individual_txns):
        """Print breakdown by source."""
        print("\n")
        print("┌" + "─" * 118 + "┐")
        print("│" + " BREAKDOWN BY SOURCE ".center(118) + "│")
        print("├" + "─" * 118 + "┤")
        
        for name, txns in [("Equity Awards Center (RSU/ESPP):", eac_txns),
                           ("Individual Brokerage (Trades):", individual_txns)]:
            ltcg = sum(t.capital_gain_inr for t in txns if t.is_long_term)
            stcg = sum(t.capital_gain_inr for t in txns if not t.is_long_term)
            print(f"│   {name}".ljust(119) + "│")
            print(f"│      Long Term Capital Gain:  ₹{ltcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Short Term Capital Gain: ₹{stcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Total:                   ₹{(ltcg + stcg):>20,.2f}".ljust(119) + "│")
            print("│".ljust(119) + "│")
        
        print("└" + "─" * 118 + "┘")
    
    def _print_type_breakdown(self, rsu_txns, espp_txns, trade_txns):
        """Print breakdown by stock type."""
        print("\n")
        print("┌" + "─" * 118 + "┐")
        print("│" + " BREAKDOWN BY STOCK TYPE ".center(118) + "│")
        print("├" + "─" * 118 + "┤")
        
        for name, txns in [("RSU (Restricted Stock Units):", rsu_txns),
                           ("ESPP (Employee Stock Purchase Plan):", espp_txns),
                           ("Regular Stock/ETF Trades:", trade_txns)]:
            ltcg = sum(t.capital_gain_inr for t in txns if t.is_long_term)
            stcg = sum(t.capital_gain_inr for t in txns if not t.is_long_term)
            print(f"│   {name}".ljust(119) + "│")
            print(f"│      Long Term Capital Gain:  ₹{ltcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Short Term Capital Gain: ₹{stcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Total:                   ₹{(ltcg + stcg):>20,.2f}".ljust(119) + "│")
            print("│".ljust(119) + "│")
        
        print("└" + "─" * 118 + "┘")
    
    def _print_symbol_breakdown(self, transactions):
        """Print breakdown by symbol."""
        symbols = set(t.symbol for t in transactions)
        if len(symbols) <= 1:
            return
        
        print("\n")
        print("┌" + "─" * 118 + "┐")
        print("│" + " BREAKDOWN BY SYMBOL ".center(118) + "│")
        print("├" + "─" * 118 + "┤")
        
        for symbol in sorted(symbols):
            sym_txns = [t for t in transactions if t.symbol == symbol]
            ltcg = sum(t.capital_gain_inr for t in sym_txns if t.is_long_term)
            stcg = sum(t.capital_gain_inr for t in sym_txns if not t.is_long_term)
            shares = sum(t.shares for t in sym_txns)
            print(f"│   {symbol}:".ljust(119) + "│")
            print(f"│      Shares Sold:             {shares:>10.2f}".ljust(119) + "│")
            print(f"│      Long Term Capital Gain:  ₹{ltcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Short Term Capital Gain: ₹{stcg:>20,.2f}".ljust(119) + "│")
            print(f"│      Total:                   ₹{(ltcg + stcg):>20,.2f}".ljust(119) + "│")
            print("│".ljust(119) + "│")
        
        print("└" + "─" * 118 + "┘")
    
    def print_quarterly_breakdown(
        self,
        transactions: List[SaleTransaction],
        indian_gains: List[IndianGains] = None,
        title: str = "QUARTERLY CAPITAL GAINS BREAKDOWN"
    ) -> Dict[str, Dict[str, QuarterlyData]]:
        """
        Print capital gains breakdown by advance tax quarters.
        
        Args:
            transactions: List of sale transactions
            indian_gains: List of Indian gains
            title: Report title
            
        Returns:
            Dictionary with quarterly data by source
        """
        indian_gains = indian_gains or []
        quarters = ADVANCE_TAX_QUARTERS
        
        # Calculate foreign quarterly data
        foreign_data = {q: QuarterlyData() for q in quarters}
        for txn in transactions:
            quarter = get_advance_tax_quarter(txn.sale_date)
            if quarter in foreign_data:
                if txn.is_long_term:
                    foreign_data[quarter].ltcg += txn.capital_gain_inr
                else:
                    foreign_data[quarter].stcg += txn.capital_gain_inr
        
        # Print Foreign Stocks table
        self._print_quarterly_table(
            "FOREIGN STOCKS (Schwab)", foreign_data,
            "(LTCG: > 2 years | STCG: ≤ 2 years)"
        )
        
        # Process Indian gains
        indian_stocks_data = {q: QuarterlyData() for q in quarters}
        indian_mf_data = {q: QuarterlyData() for q in quarters}
        
        for g in indian_gains:
            if g.source == 'Indian Stocks':
                indian_stocks_data["16 Sep-15 Dec"].ltcg = g.ltcg
                indian_stocks_data["16 Sep-15 Dec"].stcg = g.stcg
            elif 'Mutual Funds' in g.source:
                indian_mf_data["16 Sep-15 Dec"].ltcg = g.ltcg
                indian_mf_data["16 Sep-15 Dec"].stcg = g.stcg
        
        self._print_quarterly_table(
            "INDIAN STOCKS", indian_stocks_data,
            "(LTCG: > 1 year | STCG: ≤ 1 year)"
        )
        
        self._print_quarterly_table(
            "INDIAN MUTUAL FUNDS", indian_mf_data,
            "(LTCG: > 1 year | STCG: ≤ 1 year)"
        )
        
        # Combined total
        combined_data = {
            q: QuarterlyData(
                ltcg=foreign_data[q].ltcg + indian_stocks_data[q].ltcg + indian_mf_data[q].ltcg,
                stcg=foreign_data[q].stcg + indian_stocks_data[q].stcg + indian_mf_data[q].stcg
            )
            for q in quarters
        }
        
        self._print_combined_quarterly(combined_data)
        
        return {
            'foreign': foreign_data,
            'indian_stocks': indian_stocks_data,
            'indian_mf': indian_mf_data,
            'combined': combined_data
        }
    
    def _print_quarterly_table(self, source_name: str, data: Dict[str, QuarterlyData], note: str = ""):
        """Print a quarterly breakdown table."""
        quarters = ADVANCE_TAX_QUARTERS
        
        print("\n")
        print("╔" + "═" * 130 + "╗")
        title_line = f" {source_name} - Quarterly Breakdown (Advance Tax Quarters) "
        print("║" + title_line.center(130) + "║")
        if note:
            print("║" + note.center(130) + "║")
        print("╠" + "═" * 130 + "╣")
        
        # Header
        print("║" + " ".ljust(130) + "║")
        print("║   " + "Sl".ljust(5) + "Type of Capital Gain".ljust(25) + 
              "".join(q.rjust(18) for q in quarters) + "   ║")
        print("╟" + "─" * 130 + "╢")
        
        # LTCG row
        ltcg_values = [data[q].ltcg for q in quarters]
        print("║   " + "1".ljust(5) + "Long Term (LTCG)".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in ltcg_values) + "   ║")
        
        # STCG row
        stcg_values = [data[q].stcg for q in quarters]
        print("║   " + "2".ljust(5) + "Short Term (STCG)".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in stcg_values) + "   ║")
        
        print("╟" + "─" * 130 + "╢")
        
        # Total row
        total_values = [data[q].total for q in quarters]
        print("║   " + " ".ljust(5) + "TOTAL".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in total_values) + "   ║")
        
        print("╚" + "═" * 130 + "╝")
    
    def _print_combined_quarterly(self, data: Dict[str, QuarterlyData]):
        """Print combined quarterly totals with cumulative."""
        quarters = ADVANCE_TAX_QUARTERS
        
        print("\n")
        print("╔" + "═" * 130 + "╗")
        print("║" + " COMBINED TOTAL - ALL SOURCES (After Set-off) ".center(130) + "║")
        print("╠" + "═" * 130 + "╣")
        
        # Header
        print("║" + " ".ljust(130) + "║")
        print("║   " + "Sl".ljust(5) + "Type of Capital Gain".ljust(25) + 
              "".join(q.rjust(18) for q in quarters) + "   ║")
        print("╟" + "─" * 130 + "╢")
        
        # LTCG row
        ltcg_values = [data[q].ltcg for q in quarters]
        print("║   " + "1".ljust(5) + "Long Term (LTCG)".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in ltcg_values) + "   ║")
        
        # STCG row
        stcg_values = [data[q].stcg for q in quarters]
        print("║   " + "2".ljust(5) + "Short Term (STCG)".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in stcg_values) + "   ║")
        
        print("╟" + "─" * 130 + "╢")
        
        # Total row
        total_values = [data[q].total for q in quarters]
        print("║   " + " ".ljust(5) + "TOTAL".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in total_values) + "   ║")
        
        # Cumulative totals
        print("║" + " ".ljust(130) + "║")
        print("╟" + "─" * 130 + "╢")
        
        # Cumulative LTCG
        cum_ltcg = [sum(ltcg_values[:i+1]) for i in range(len(ltcg_values))]
        print("║   " + " ".ljust(5) + "Cumulative LTCG".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in cum_ltcg) + "   ║")
        
        # Cumulative STCG
        cum_stcg = [sum(stcg_values[:i+1]) for i in range(len(stcg_values))]
        print("║   " + " ".ljust(5) + "Cumulative STCG".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in cum_stcg) + "   ║")
        
        # Cumulative Total
        cum_total = [sum(total_values[:i+1]) for i in range(len(total_values))]
        print("║   " + " ".ljust(5) + "Cumulative Total".ljust(25) + 
              "".join(f"₹{v:>15,.0f}".rjust(18) for v in cum_total) + "   ║")
        
        print("╚" + "═" * 130 + "╝")
    
    def print_grand_total(
        self,
        transactions: List[SaleTransaction],
        indian_gains: List[IndianGains]
    ) -> None:
        """Print grand total from all sources."""
        schwab_ltcg = sum(t.capital_gain_inr for t in transactions if t.is_long_term)
        schwab_stcg = sum(t.capital_gain_inr for t in transactions if not t.is_long_term)
        
        indian_ltcg = sum(g.ltcg for g in indian_gains)
        indian_stcg = sum(g.stcg for g in indian_gains)
        
        total_ltcg = schwab_ltcg + indian_ltcg
        total_stcg = schwab_stcg + indian_stcg
        
        print("\n")
        print("╔" + "═" * 90 + "╗")
        print("║" + " GRAND TOTAL CAPITAL GAINS (ALL SOURCES) ".center(90) + "║")
        print("╠" + "═" * 90 + "╣")
        print("║" + " ".ljust(90) + "║")
        print("║   " + "Source".ljust(40) + "LTCG (INR)".rjust(22) + "STCG (INR)".rjust(22) + "   ║")
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'Schwab (RSU/ESPP/Trades)'.ljust(40)}₹{schwab_ltcg:>18,.2f}  ₹{schwab_stcg:>18,.2f}   ║")
        
        for g in indian_gains:
            print(f"║   {g.source.ljust(40)}₹{g.ltcg:>18,.2f}  ₹{g.stcg:>18,.2f}   ║")
        
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'GRAND TOTAL'.ljust(40)}₹{total_ltcg:>18,.2f}  ₹{total_stcg:>18,.2f}   ║")
        print("║" + " ".ljust(90) + "║")
        print(f"║   {'TOTAL CAPITAL GAINS'.ljust(40)}₹{(total_ltcg + total_stcg):>41,.2f}   ║")
        print("╚" + "═" * 90 + "╝")

