"""
Parsers for Schwab transaction files.

This module provides parsers for Schwab Equity Awards Center (EAC)
and Individual Brokerage account transaction files.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from typing import List, Dict

from ..models import SaleTransaction, StockLot
from ..utils import parse_currency, parse_date


class BaseSchwabParser(ABC):
    """Abstract base class for Schwab transaction parsers."""
    
    # Foreign stocks use 2-year holding period for LTCG classification
    LONG_TERM_DAYS = 2 * 365  # >730 days = Long Term
    
    @abstractmethod
    def parse(self, transactions: List[Dict], start_date: datetime) -> List[SaleTransaction]:
        """
        Parse transactions and return sale transactions.
        
        Args:
            transactions: List of transaction dictionaries from JSON
            start_date: Only include transactions on or after this date
            
        Returns:
            List of SaleTransaction objects
        """
        pass
    
    def _is_long_term(self, holding_days: int) -> bool:
        """Check if holding period qualifies as long-term."""
        return holding_days > self.LONG_TERM_DAYS


class SchwabEACParser(BaseSchwabParser):
    """
    Parser for Schwab Equity Awards Center (EAC) transactions.
    
    Handles RSU (Restricted Stock) and ESPP transactions.
    
    Expected JSON format:
    {
        "Transactions": [
            {
                "Action": "Sale",
                "Date": "12/01/2025",
                "Symbol": "AAPL",
                "FeesAndCommissions": "$10.00",
                "TransactionDetails": [
                    {
                        "Details": {
                            "Type": "RS",
                            "Shares": "100",
                            "SalePrice": "$150.00",
                            "GrossProceeds": "$15000.00",
                            "VestDate": "01/15/2023",
                            "VestFairMarketValue": "$120.00",
                            "GrantId": "G123456"
                        }
                    }
                ]
            }
        ]
    }
    """
    
    def parse(self, transactions: List[Dict], start_date: datetime) -> List[SaleTransaction]:
        """
        Parse EAC transactions and extract sale transactions.
        
        Args:
            transactions: List of transaction dictionaries
            start_date: Filter transactions from this date onwards
            
        Returns:
            List of SaleTransaction objects for sales after start_date
        """
        sale_transactions = []
        
        for txn in transactions:
            if txn.get("Action") != "Sale":
                continue
            
            sale_date = parse_date(txn["Date"])
            
            # Filter transactions from start_date onwards
            if sale_date < start_date:
                continue
            
            symbol = txn.get("Symbol", "")
            
            # Get total fees and commissions for this sale
            total_fees_usd = parse_currency(txn.get("FeesAndCommissions", "0"))
            
            # Count total shares for proportional fee distribution
            total_shares_in_txn = sum(
                int(dw.get("Details", {}).get("Shares", 0))
                for dw in txn.get("TransactionDetails", [])
            )
            
            # Process each transaction detail (individual lot sales)
            for detail_wrapper in txn.get("TransactionDetails", []):
                details = detail_wrapper.get("Details", {})
                
                shares = int(details.get("Shares", 0))
                if shares == 0:
                    continue
                
                stock_type = details.get("Type", "")
                sale_price = parse_currency(details.get("SalePrice", "0"))
                gross_proceeds = parse_currency(details.get("GrossProceeds", "0"))
                
                # Distribute fees proportionally
                fees_for_lot = (
                    (total_fees_usd * shares / total_shares_in_txn)
                    if total_shares_in_txn > 0 else 0
                )
                
                # Parse acquisition date and price based on stock type
                sale_txn = self._create_transaction(
                    details, stock_type, sale_date, symbol, shares,
                    sale_price, gross_proceeds, fees_for_lot
                )
                
                if sale_txn:
                    sale_transactions.append(sale_txn)
        
        return sale_transactions
    
    def _create_transaction(
        self, details: Dict, stock_type: str, sale_date: datetime,
        symbol: str, shares: int, sale_price: float, gross_proceeds: float,
        fees: float
    ) -> SaleTransaction:
        """Create a SaleTransaction from parsed details."""
        
        if stock_type == "RS":  # RSU - Restricted Stock
            vest_date_str = details.get("VestDate", "")
            vest_fmv_str = details.get("VestFairMarketValue", "0")
            
            if not vest_date_str:
                return None
            
            acquisition_date = parse_date(vest_date_str)
            acquisition_price = parse_currency(vest_fmv_str)
            
        elif stock_type == "ESPP":
            purchase_date_str = details.get("PurchaseDate", "")
            purchase_fmv_str = details.get("PurchaseFairMarketValue", "0")
            
            if not purchase_date_str:
                return None
            
            acquisition_date = parse_date(purchase_date_str)
            acquisition_price = parse_currency(purchase_fmv_str)
            
        else:
            return None  # Skip unknown types
        
        holding_period = (sale_date - acquisition_date).days
        
        return SaleTransaction(
            sale_date=sale_date,
            acquisition_date=acquisition_date,
            stock_type=stock_type,
            symbol=symbol,
            shares=shares,
            sale_price_usd=sale_price,
            acquisition_price_usd=acquisition_price,
            gross_proceeds_usd=gross_proceeds,
            grant_id=details.get("GrantId"),
            source="EAC",
            fees_and_commissions_usd=fees,
            holding_period_days=holding_period,
            is_long_term=self._is_long_term(holding_period)
        )


class SchwabIndividualParser(BaseSchwabParser):
    """
    Parser for Schwab Individual Brokerage account transactions.
    
    Uses FIFO (First-In-First-Out) matching for cost basis determination.
    
    Expected JSON format:
    {
        "BrokerageTransactions": [
            {
                "Action": "Buy",
                "Date": "01/15/2023",
                "Symbol": "VTI",
                "Quantity": "50",
                "Price": "$200.00"
            },
            {
                "Action": "Sell",
                "Date": "12/01/2025",
                "Symbol": "VTI",
                "Quantity": "50",
                "Price": "$250.00",
                "Fees & Comm": "$5.00"
            }
        ]
    }
    """
    
    def parse(self, transactions: List[Dict], start_date: datetime) -> List[SaleTransaction]:
        """
        Parse Individual Brokerage transactions using FIFO matching.
        
        Args:
            transactions: List of transaction dictionaries
            start_date: Filter sales from this date onwards
            
        Returns:
            List of SaleTransaction objects
            
        Note:
            All transactions (including before start_date) are processed
            to maintain accurate FIFO lot tracking.
        """
        sale_transactions = []
        
        # Build inventory of purchases (lots) by symbol
        lots_by_symbol: Dict[str, List[StockLot]] = defaultdict(list)
        
        # Sort transactions by date (oldest first for FIFO)
        sorted_txns = sorted(transactions, key=lambda x: parse_date(x["Date"]))
        
        for txn in sorted_txns:
            action = txn.get("Action", "")
            symbol = txn.get("Symbol", "")
            
            if not symbol:
                continue
            
            quantity_str = txn.get("Quantity", "0")
            if not quantity_str:
                continue
            quantity = float(quantity_str)
            
            date = parse_date(txn["Date"])
            price = parse_currency(txn.get("Price", "0"))
            
            if action in ("Buy", "Reinvest Shares"):
                # Add to inventory
                lot = StockLot(
                    purchase_date=date,
                    symbol=symbol,
                    quantity=quantity,
                    price=price
                )
                lots_by_symbol[symbol].append(lot)
                
            elif action == "Sell":
                sales = self._process_sale(
                    txn, date, symbol, quantity, price,
                    lots_by_symbol[symbol], start_date
                )
                sale_transactions.extend(sales)
        
        return sale_transactions
    
    def _process_sale(
        self, txn: Dict, sale_date: datetime, symbol: str,
        quantity: float, sale_price: float, lots: List[StockLot],
        start_date: datetime
    ) -> List[SaleTransaction]:
        """Process a sell transaction using FIFO matching."""
        
        sales = []
        fees_str = txn.get("Fees & Comm", "0")
        total_fees_usd = parse_currency(fees_str) if fees_str else 0.0
        
        # For pre-start_date sales, just consume lots without recording
        if sale_date < start_date:
            remaining = quantity
            for lot in lots:
                if lot.remaining <= 0:
                    continue
                sold_from_lot = min(lot.remaining, remaining)
                lot.remaining -= sold_from_lot
                remaining -= sold_from_lot
                if remaining <= 0:
                    break
            return []
        
        # Match with purchased lots using FIFO
        remaining_to_sell = quantity
        total_quantity = quantity
        
        for lot in lots:
            if lot.remaining <= 0:
                continue
            
            sold_from_lot = min(lot.remaining, remaining_to_sell)
            lot.remaining -= sold_from_lot
            remaining_to_sell -= sold_from_lot
            
            # Distribute fees proportionally
            fees_for_lot = (
                (total_fees_usd * sold_from_lot / total_quantity)
                if total_quantity > 0 else 0
            )
            
            holding_period = (sale_date - lot.purchase_date).days
            
            sale_txn = SaleTransaction(
                sale_date=sale_date,
                acquisition_date=lot.purchase_date,
                stock_type="TRADE",
                symbol=symbol,
                shares=sold_from_lot,
                sale_price_usd=sale_price,
                acquisition_price_usd=lot.price,
                gross_proceeds_usd=sale_price * sold_from_lot,
                grant_id=None,
                source="Individual",
                fees_and_commissions_usd=fees_for_lot,
                holding_period_days=holding_period,
                is_long_term=self._is_long_term(holding_period)
            )
            sales.append(sale_txn)
            
            if remaining_to_sell <= 0:
                break
        
        # Warn about unmatched shares
        if remaining_to_sell > 0:
            print(
                f"  Warning: {remaining_to_sell:.3f} shares of {symbol} sold on "
                f"{sale_date.strftime('%d-%b-%Y')} have no matching purchase - "
                "assuming older purchase with unknown cost basis"
            )
        
        return sales

