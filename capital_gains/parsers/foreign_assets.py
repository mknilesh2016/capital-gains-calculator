"""
Parsers for foreign assets data (Schwab EAC and Brokerage files).
Used for Schedule FA generation.
"""

import json
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from io import StringIO


class ForeignAssetsParser:
    """
    Parser for foreign assets data from Schwab exports.
    Handles both EAC (Equity Awards Center) and Individual Brokerage files.
    """
    
    def __init__(self, calendar_year: int):
        self.calendar_year = calendar_year
        self.cy_start = datetime(calendar_year, 1, 1)
        self.cy_end = datetime(calendar_year, 12, 31)
    
    @staticmethod
    def parse_date(date_str: str) -> datetime:
        """Parse date string to datetime - handles multiple formats."""
        formats = ['%m/%d/%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        raise ValueError(f"Could not parse date: {date_str}")
    
    @staticmethod
    def parse_amount(value: str) -> float:
        """Parse monetary amount from string."""
        if not value:
            return 0.0
        clean = str(value).replace('$', '').replace(',', '').strip()
        try:
            return float(clean)
        except ValueError:
            return 0.0
    
    def parse_eac_transactions(self, content: dict) -> Dict[str, Any]:
        """
        Parse Schwab EAC transactions JSON file.
        
        Returns dict with:
        - sales: Regular stock sales
        - tax_sales: Tax withholding sales (same-day)
        - dividends: Dividend payments with tax withheld
        - symbol: Primary stock symbol
        """
        transactions = content.get('Transactions', [])
        sales = []
        tax_sales = []
        dividends = []
        symbol = 'NVDA'  # Default, will be overwritten
        
        # First pass: collect dividends and tax withholdings by date
        dividend_by_date = {}  # date -> {symbol, gross}
        tax_withholding_by_date = {}  # date -> tax amount
        
        for txn in transactions:
            action = txn.get('Action', '')
            txn_date_str = txn.get('Date', '')
            
            if not txn_date_str:
                continue
            
            txn_date = self.parse_date(txn_date_str)
            
            # Only process transactions in the calendar year
            if not (self.cy_start <= txn_date <= self.cy_end):
                continue
            
            # Get symbol from first transaction with one
            if txn.get('Symbol'):
                symbol = txn.get('Symbol')
            
            # Collect dividend amounts
            if action == 'Dividend':
                amount = self.parse_amount(txn.get('Amount', '0'))
                if amount > 0:
                    dividend_by_date[txn_date_str] = {
                        'symbol': symbol,
                        'gross': amount,
                    }
            
            # Collect tax withholding amounts (paired with dividends)
            elif action == 'Tax Withholding':
                amount = abs(self.parse_amount(txn.get('Amount', '0')))
                if amount > 0:
                    tax_withholding_by_date[txn_date_str] = amount
        
        # Combine dividends with their tax withholdings
        for date_str, div_info in dividend_by_date.items():
            tax = tax_withholding_by_date.get(date_str, 0)
            dividends.append({
                'symbol': div_info['symbol'],
                'date': date_str,
                'gross': div_info['gross'],
                'tax': tax,
                'source': 'Equity Awards',
            })
        
        # Second pass: process other transactions
        for txn in transactions:
            action = txn.get('Action', '')
            txn_date_str = txn.get('Date', '')
            
            if not txn_date_str:
                continue
            
            txn_date = self.parse_date(txn_date_str)
            
            # Only process transactions in the calendar year
            if not (self.cy_start <= txn_date <= self.cy_end):
                continue
            
            # Get symbol
            if txn.get('Symbol'):
                symbol = txn.get('Symbol')
            
            # Regular Sales
            if action == 'Sale':
                for detail in txn.get('TransactionDetails', []):
                    d = detail.get('Details', {})
                    txn_type = d.get('Type', '')
                    shares = int(d.get('Shares', '0') or '0')
                    
                    if shares == 0:
                        continue
                    
                    if txn_type == 'ESPP':
                        sales.append({
                            'type': 'ESPP',
                            'symbol': symbol,
                            'vest_date': d.get('PurchaseDate', ''),
                            'grant_id': '-',
                            'shares': shares,
                            'fmv': self.parse_amount(d.get('PurchasePrice', '0')),
                            'sale_price': self.parse_amount(d.get('SalePrice', '0')),
                            'proceeds': self.parse_amount(d.get('GrossProceeds', '0')),
                            'sale_date': txn_date_str,
                        })
                    elif txn_type == 'RS':
                        sales.append({
                            'type': 'RSU',
                            'symbol': symbol,
                            'vest_date': d.get('VestDate', ''),
                            'grant_id': d.get('GrantId', ''),
                            'shares': shares,
                            'fmv': self.parse_amount(d.get('VestFairMarketValue', '0')),
                            'sale_price': self.parse_amount(d.get('SalePrice', '0')),
                            'proceeds': self.parse_amount(d.get('GrossProceeds', '0')),
                            'sale_date': txn_date_str,
                        })
            
            # Tax withholding sales (Lapse)
            elif action == 'Lapse':
                for detail in txn.get('TransactionDetails', []):
                    d = detail.get('Details', {})
                    shares_tax = int(d.get('SharesSoldWithheldForTaxes', '0') or '0')
                    if shares_tax == 0:
                        continue
                    
                    tax_sales.append({
                        'type': 'RSU-TAX',
                        'symbol': symbol,
                        'date': txn_date_str,
                        'grant_id': d.get('AwardId', ''),
                        'shares': shares_tax,
                        'fmv': self.parse_amount(d.get('FairMarketValuePrice', '0')),
                    })
            
            # ESPP Tax withholding
            elif action == 'Deposit' and txn.get('Description') == 'ESPP':
                for detail in txn.get('TransactionDetails', []):
                    d = detail.get('Details', {})
                    shares_withheld = int(d.get('SharesWithheld', '0') or '0')
                    if shares_withheld == 0:
                        continue
                    
                    tax_sales.append({
                        'type': 'ESPP-TAX',
                        'symbol': symbol,
                        'date': txn_date_str,
                        'grant_id': 'ESPP',
                        'shares': shares_withheld,
                        'fmv': self.parse_amount(d.get('PurchaseFairMarketValue', '0')),
                    })
        
        return {
            'sales': sales,
            'tax_sales': tax_sales,
            'dividends': dividends,
            'symbol': symbol,
        }
    
    def parse_holdings_csv(self, content: str, symbol: str = 'NVDA') -> List[Dict[str, Any]]:
        """
        Parse Schwab EAC holdings CSV file.
        
        Returns list of held share lots.
        """
        held_shares = []
        
        lines = content.split('\n')
        reader = csv.reader(lines)
        rows = list(reader)
        
        in_espp_section = False
        in_rsu_section = False
        
        for row in rows:
            if len(row) < 5:
                continue
            
            row_str = ','.join(row)
            
            # Detect section changes
            if 'Purchase Date,Symbol,Market Value' in row_str:
                in_espp_section = True
                in_rsu_section = False
                continue
            elif 'Award Date,Symbol,Award ID,Share Type' in row_str:
                in_espp_section = False
                in_rsu_section = True
                continue
            elif 'Date Holding Period Met,Symbol,Plan Id' in row_str:
                continue
            elif 'Totals' in row_str:
                continue
            
            try:
                # ESPP Section Format:
                # Purchase Date, Symbol, Market Value, Deposit Date, Purchase Price, Holding Status, Shares Purchased, Available
                if in_espp_section and len(row) >= 8:
                    avail_str = row[-1].replace(',', '').replace('"', '').strip()
                    if not avail_str.isdigit():
                        continue
                    available = int(avail_str)
                    if available <= 0:
                        continue
                    
                    purchase_date = row[0].replace('"', '').strip()
                    purchase_price_str = row[4].replace('"', '').replace('$', '').replace(',', '').strip()
                    
                    try:
                        cost = float(purchase_price_str)
                    except (ValueError, IndexError):
                        continue
                    
                    if purchase_date and cost > 0:
                        date_str = purchase_date.replace('-', '/')
                        held_shares.append({
                            "type": "ESPP",
                            "symbol": symbol,
                            "date": date_str,
                            "shares": available,
                            "cost": cost
                        })
                
                # RSU Section Format:
                # Award Date, Symbol, Award ID, Type, Market Value, N/A, Deposit Date, Vest Date, FMV, Shares, Available
                elif in_rsu_section and len(row) >= 10:
                    avail_str = row[-1].replace(',', '').replace('"', '').strip()
                    if not avail_str.isdigit():
                        continue
                    available = int(avail_str)
                    if available <= 0:
                        continue
                    
                    # Check if this is an RSU data row
                    award_type = row[3].replace('"', '').strip() if len(row) > 3 else ''
                    if 'Restricted' not in award_type and 'RS' not in award_type:
                        continue
                    
                    vest_date = row[7].replace('"', '').strip() if len(row) > 7 else ''
                    fmv_str = row[8].replace('"', '').replace('$', '').replace(',', '').strip() if len(row) > 8 else '0'
                    
                    try:
                        cost = float(fmv_str)
                    except (ValueError, IndexError):
                        continue
                    
                    if vest_date and cost > 0:
                        date_str = vest_date.replace('-', '/')
                        held_shares.append({
                            "type": "RSU",
                            "symbol": symbol,
                            "date": date_str,
                            "shares": available,
                            "cost": cost
                        })
            
            except Exception:
                continue
        
        return held_shares
    
    def parse_brokerage_transactions(self, content: dict) -> Dict[str, Any]:
        """
        Parse Schwab Individual Brokerage transactions JSON file.
        
        Returns dict with:
        - holdings: Aggregated holdings by symbol
        - transactions: Individual buy/sell transactions
        - dividends: Dividend payments with tax withheld
        """
        holdings = defaultdict(lambda: {
            'symbol': '', 'description': '', 'shares': 0.0, 'cost_basis': 0.0,
            'first_buy_date': None, 'dividends': 0.0, 'tax_withheld': 0.0,
            'sales_proceeds': 0.0, 'shares_sold': 0.0,
        })
        transactions = []
        
        # First pass: collect dividends and NRA withholdings by (symbol, date)
        # to properly link tax withheld to dividend payments
        dividend_entries = {}  # (symbol, date) -> {gross, source}
        nra_withholdings = {}  # (symbol, date) -> tax amount
        
        for txn in content.get('BrokerageTransactions', []):
            action = txn['Action']
            symbol = txn.get('Symbol', '')
            if not symbol:
                continue
            
            amount = self.parse_amount(txn.get('Amount', '0'))
            date = txn['Date']
            
            # Filter by calendar year
            try:
                txn_date = self.parse_date(date)
                if not (self.cy_start <= txn_date <= self.cy_end):
                    continue
            except ValueError:
                continue
            
            key = (symbol, date)
            
            # Collect dividend/cap gain amounts
            if 'Dividend' in action or 'Cap Gain' in action:
                if amount > 0:
                    if key in dividend_entries:
                        dividend_entries[key]['gross'] += amount
                    else:
                        dividend_entries[key] = {
                            'symbol': symbol,
                            'date': date,
                            'gross': amount,
                            'source': 'Brokerage',
                        }
            
            # Collect NRA withholdings
            elif action in ['NRA Withholding', 'NRA Tax Adj']:
                tax_amt = abs(amount)
                if key in nra_withholdings:
                    nra_withholdings[key] += tax_amt
                else:
                    nra_withholdings[key] = tax_amt
        
        # Combine dividends with their NRA withholdings
        dividends = []
        for key, div_info in dividend_entries.items():
            symbol, date = key
            tax = nra_withholdings.get(key, 0)
            dividends.append({
                'symbol': div_info['symbol'],
                'date': div_info['date'],
                'gross': div_info['gross'],
                'tax': tax,
                'source': div_info['source'],
            })
        
        # Second pass: process buy/sell transactions and update holdings
        for txn in content.get('BrokerageTransactions', []):
            action = txn['Action']
            symbol = txn.get('Symbol', '')
            if not symbol:
                continue
            
            amount = self.parse_amount(txn.get('Amount', '0'))
            qty_str = txn.get('Quantity', '')
            qty = float(qty_str) if qty_str else 0.0
            price_str = txn.get('Price', '')
            price = self.parse_amount(price_str) if price_str else 0.0
            desc = txn.get('Description', '')
            date = txn['Date']
            
            # Filter by calendar year
            try:
                txn_date = self.parse_date(date)
                if not (self.cy_start <= txn_date <= self.cy_end):
                    continue
            except ValueError:
                continue
            
            h = holdings[symbol]
            h['symbol'] = symbol
            h['description'] = desc
            
            if action in ['Buy', 'Reinvest Shares']:
                h['shares'] += qty
                h['cost_basis'] += abs(amount)
                if h['first_buy_date'] is None:
                    h['first_buy_date'] = date
                # Track individual buy
                if qty > 0:
                    transactions.append({
                        'action': 'Buy',
                        'symbol': symbol,
                        'description': desc,
                        'date': date,
                        'shares': qty,
                        'price': price,
                        'amount': abs(amount),
                        'is_reinvest': action == 'Reinvest Shares',
                    })
            elif action == 'Sell':
                h['shares'] -= qty
                h['shares_sold'] += qty
                h['sales_proceeds'] += amount
                # Track individual sell
                if qty > 0:
                    transactions.append({
                        'action': 'Sell',
                        'symbol': symbol,
                        'description': desc,
                        'date': date,
                        'shares': qty,
                        'price': price,
                        'amount': amount,
                        'is_reinvest': False,
                    })
            elif 'Dividend' in action or 'Cap Gain' in action:
                h['dividends'] += amount
            elif action in ['NRA Withholding', 'NRA Tax Adj']:
                h['tax_withheld'] += abs(amount)
        
        # Sort transactions by date
        transactions.sort(key=lambda x: self.parse_date(x['date']))
        
        # Sort dividends by date
        dividends.sort(key=lambda x: self.parse_date(x['date']))
        
        return {
            'holdings': dict(holdings),
            'transactions': transactions,
            'dividends': dividends,
        }
    
    def parse_from_zip(self, zip_file) -> Dict[str, Any]:
        """
        Parse foreign assets data from a ZIP file.
        
        Expected ZIP contents:
        - *_Transactions_*.json (EAC transactions)
        - *_EquityDetails_*.csv (Holdings)
        - Individual_*_Transactions_*.json (Brokerage - optional)
        - sbi_reference_rates.json (Exchange rates - optional)
        
        Returns combined parsed data.
        """
        import zipfile
        import io
        
        result = {
            'eac_data': None,
            'holdings': [],
            'brokerage_data': None,
            'exchange_rates': None,
        }
        
        zip_bytes = io.BytesIO(zip_file.read())
        
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            for filename in zf.namelist():
                filename_lower = filename.lower()
                
                try:
                    with zf.open(filename) as f:
                        content = f.read().decode('utf-8', errors='ignore')
                        
                        if 'transaction' in filename_lower and filename_lower.endswith('.json'):
                            data = json.loads(content)
                            
                            if 'individual' in filename_lower or 'brokerage' in filename_lower:
                                # Brokerage transactions
                                result['brokerage_data'] = self.parse_brokerage_transactions(data)
                            elif 'equityawardscenter' in filename_lower or 'eac' in filename_lower:
                                # EAC transactions
                                result['eac_data'] = self.parse_eac_transactions(data)
                        
                        elif 'equitydetails' in filename_lower and filename_lower.endswith('.csv'):
                            # Holdings CSV
                            symbol = result['eac_data']['symbol'] if result['eac_data'] else 'NVDA'
                            result['holdings'] = self.parse_holdings_csv(content, symbol)
                        
                        elif 'sbi' in filename_lower and filename_lower.endswith('.json'):
                            # Exchange rates
                            result['exchange_rates'] = json.loads(content)
                
                except Exception as e:
                    print(f"Warning: Error processing {filename}: {e}")
                    continue
        
        return result

