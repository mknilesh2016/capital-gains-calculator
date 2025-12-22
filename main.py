#!/usr/bin/env python3
"""
Capital Gains Calculator - Main Entry Point

A comprehensive tool for calculating capital gains from stock sales,
designed for Indian residents with investments in both foreign (US) and Indian markets.

Usage:
    python main.py
    python main.py --taxes-paid 475000
    python main.py --eac path/to/eac.json --individual path/to/trades.json
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Set UTF-8 encoding for console output (fixes Windows encoding issues)
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from capital_gains import (
    CapitalGainsCalculator,
    TaxCalculator,
    TaxRates,
    IndianGains,
)
from capital_gains.parsers import (
    SchwabEACParser,
    SchwabIndividualParser,
    IndianStocksParser,
    IndianMutualFundsParser,
    ZerodhaPnLParser,
)
from capital_gains.reports import ConsoleReporter, ExcelReporter
from capital_gains.utils import find_file_in_statements


# EULA configuration
EULA_CONFIG_FILE = Path.home() / ".capital_gains_calculator" / "eula_accepted"

EULA_TEXT = """
================================================================================
                     END USER LICENSE AGREEMENT (EULA)
================================================================================

Please read the following terms carefully before using the Capital Gains Calculator.

1. NON-COMMERCIAL USE ONLY
   This tool is provided exclusively for personal, non-commercial use. You may 
   not use this software for commercial purposes, redistribute it for profit, 
   or incorporate it into commercial products or services.

2. NO WARRANTY OR GUARANTEE
   This calculator is provided "AS IS" without any warranty of any kind, either 
   express or implied. The calculations are provided for informational purposes 
   only and may contain errors, inaccuracies, or omissions.

3. NOT PROFESSIONAL TAX ADVICE
   This tool does NOT constitute professional tax, financial, or legal advice. 
   The output should not be solely relied upon for tax filing or any financial 
   decisions. Always verify all calculations with a qualified Chartered 
   Accountant (CA) or tax professional before filing your tax returns.

4. TAX RATE ASSUMPTIONS
   This calculator uses the New Tax Regime with 39% effective rate (30% slab + 
   25% surcharge + 4% cess) for foreign STCG, assuming income above Rs.2 Crore. 
   Your actual tax rates may differ based on your specific circumstances.

5. LIMITATION OF LIABILITY
   Under no circumstances shall the developers be liable for any direct, indirect, 
   incidental, special, consequential, or punitive damages arising from the use 
   of this calculator, including but not limited to any errors in tax calculations, 
   missed deadlines, penalties, or interest charges from tax authorities.

6. USER RESPONSIBILITY
   You are solely responsible for verifying all calculations and ensuring 
   compliance with applicable tax laws.

================================================================================
"""


def check_eula_accepted() -> bool:
    """Check if EULA has been previously accepted."""
    return EULA_CONFIG_FILE.exists()


def save_eula_acceptance():
    """Save EULA acceptance to config file."""
    EULA_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    EULA_CONFIG_FILE.write_text(f"accepted={datetime.now().isoformat()}")


def prompt_eula_acceptance() -> bool:
    """Display EULA and prompt for acceptance. Returns True if accepted."""
    print(EULA_TEXT)
    
    print("By typing 'ACCEPT' below, you acknowledge that you have read,")
    print("understood, and agree to the above terms and conditions.")
    print()
    
    try:
        response = input("Type ACCEPT to continue (or press Ctrl+C to exit): ").strip()
        if response.upper() == "ACCEPT":
            save_eula_acceptance()
            print()
            print("[✓] EULA accepted. You won't be prompted again on this machine.")
            print()
            return True
        else:
            print()
            print("[✗] EULA not accepted. Exiting...")
            return False
    except (KeyboardInterrupt, EOFError):
        print()
        print("[✗] Operation cancelled. Exiting...")
        return False


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Capital Gains Calculator for Schwab & Indian Brokers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py
    (Uses default files from statements folder)
    
  python main.py --taxes-paid 4750000
    (Specify taxes already paid as INR 47.5 lakhs)
    
  python main.py --eac path/to/eac.json --individual path/to/individual.json
    (Specify Schwab files)
"""
    )
    
    parser.add_argument('--eac', '-e', dest='eac_file',
                        help='Path to Schwab EquityAwardsCenter transactions JSON file')
    parser.add_argument('--individual', '-i', dest='individual_file',
                        help='Path to Schwab Individual Brokerage transactions JSON file')
    parser.add_argument('--mf', '-m', dest='mf_file',
                        help='Path to Groww Mutual Funds capital gains XLSX file')
    parser.add_argument('--stocks', '-s', dest='stocks_file',
                        help='Path to Groww Stocks capital gains XLSX file')
    parser.add_argument('--zerodha', '-z', dest='zerodha_file',
                        help='Path to Zerodha P&L report XLSX file')
    parser.add_argument('--sbi-rates', '-r', dest='sbi_rates_file',
                        help='Path to SBI TT Buy USD-INR rates JSON file')
    parser.add_argument('--start-date', dest='start_date', default='2025-04-01',
                        help='Start date for calculation (YYYY-MM-DD, default: 2025-04-01)')
    parser.add_argument('--taxes-paid', '-t', dest='taxes_paid', type=float, default=0.0,
                        help='Taxes already paid in INR (default: 0)')
    parser.add_argument('--show-eula', action='store_true',
                        help='Show the EULA/disclaimer terms')
    parser.add_argument('--reset-eula', action='store_true',
                        help='Reset EULA acceptance and prompt again')
    
    return parser


def find_input_files(args, statements_folder: str) -> dict:
    """Find all input files based on arguments or defaults."""
    files = {
        'eac': args.eac_file or find_file_in_statements(
            "EquityAwardsCenter_Transactions*.json", statements_folder),
        'individual': args.individual_file or find_file_in_statements(
            "Individual_*_Transactions*.json", statements_folder),
        'mf': args.mf_file or find_file_in_statements(
            "Mutual_Funds_Capital_Gains_Report*.xlsx", statements_folder),
        'stocks': args.stocks_file or find_file_in_statements(
            "Stocks_Capital_Gains_Report*.xlsx", statements_folder),
        'zerodha': args.zerodha_file or find_file_in_statements(
            "pnl-*.xlsx", statements_folder),
        'sbi_rates': args.sbi_rates_file or find_file_in_statements(
            "sbi_reference_rates.json", statements_folder),
    }
    return files


def print_header(start_date: datetime, files: dict, taxes_paid: float):
    """Print the application header."""
    print("=" * 80)
    print("  CAPITAL GAINS CALCULATOR")
    print("=" * 80)
    print(f"\n[*] Calculating gains from: {start_date.strftime('%d %B %Y')}")
    
    print("\n[*] Input Files:")
    print(f"   EAC Transactions:        {files['eac'] or 'Not found'}")
    print(f"   Individual Transactions: {files['individual'] or 'Not found'}")
    print(f"   Groww Mutual Funds:      {files['mf'] or 'Not found'}")
    print(f"   Groww Stocks:            {files['stocks'] or 'Not found'}")
    print(f"   Zerodha P&L:             {files['zerodha'] or 'Not found'}")
    print(f"   SBI USD-INR Rates:       {files['sbi_rates'] or 'Not found'}")
    print(f"\n[*] Taxes Already Paid:      Rs.{taxes_paid:,.2f}")


def main():
    """Main function to run the capital gains calculator."""
    # Parse arguments first to check for EULA-related flags
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Handle --show-eula flag
    if args.show_eula:
        print(EULA_TEXT)
        return
    
    # Handle --reset-eula flag
    if args.reset_eula:
        if EULA_CONFIG_FILE.exists():
            EULA_CONFIG_FILE.unlink()
            print("[✓] EULA acceptance has been reset.")
            print("    You will be prompted to accept the EULA on next run.")
        else:
            print("[*] EULA was not previously accepted.")
        return
    
    # Check EULA acceptance
    if not check_eula_accepted():
        if not prompt_eula_acceptance():
            return
    
    # Setup directories
    script_dir = os.path.dirname(os.path.abspath(__file__))
    statements_folder = os.path.join(script_dir, "statements")
    
    if not os.path.exists(statements_folder):
        os.makedirs(statements_folder)
        print(f"[+] Created statements folder: {statements_folder}")
    
    # Parse start date
    try:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    except ValueError:
        print(f"[ERROR] Invalid date format: {args.start_date}. Use YYYY-MM-DD format.")
        return
    
    # Find input files
    files = find_input_files(args, statements_folder)
    
    # Print header
    print_header(start_date, files, args.taxes_paid)
    
    # Initialize parsers
    eac_parser = SchwabEACParser()
    individual_parser = SchwabIndividualParser()
    stocks_parser = IndianStocksParser()
    mf_parser = IndianMutualFundsParser()
    zerodha_parser = ZerodhaPnLParser()
    
    all_transactions = []
    indian_gains = []
    
    # Process EAC file
    if files['eac'] and os.path.exists(files['eac']):
        print(f"\n[+] Loading EAC transactions from: {os.path.basename(files['eac'])}")
        with open(files['eac'], 'r') as f:
            eac_data = json.load(f)
        
        eac_transactions = eac_data.get("Transactions", [])
        print(f"    Total transactions in file: {len(eac_transactions)}")
        
        eac_sales = eac_parser.parse(eac_transactions, start_date)
        print(f"    Sale transactions from {start_date.strftime('%d-%b-%Y')}: {len(eac_sales)}")
        all_transactions.extend(eac_sales)
    elif files['eac']:
        print(f"\n[WARN] EAC file not found: {files['eac']}")
    
    # Process Individual file
    if files['individual'] and os.path.exists(files['individual']):
        print(f"\n[+] Loading Individual transactions from: {os.path.basename(files['individual'])}")
        with open(files['individual'], 'r') as f:
            individual_data = json.load(f)
        
        individual_transactions = individual_data.get("BrokerageTransactions", [])
        print(f"    Total transactions in file: {len(individual_transactions)}")
        
        individual_sales = individual_parser.parse(individual_transactions, start_date)
        print(f"    Sale transactions from {start_date.strftime('%d-%b-%Y')}: {len(individual_sales)}")
        all_transactions.extend(individual_sales)
    elif files['individual']:
        print(f"\n[WARN] Individual file not found: {files['individual']}")
    
    # Process Indian Stocks file
    if files['stocks'] and os.path.exists(files['stocks']):
        print(f"\n[+] Loading Indian Stocks from: {os.path.basename(files['stocks'])}")
        indian_stocks = stocks_parser.parse(files['stocks'])
        indian_gains.append(indian_stocks)
    elif files['stocks']:
        print(f"\n[WARN] Indian Stocks file not found: {files['stocks']}")
    
    # Process Indian MF file
    if files['mf'] and os.path.exists(files['mf']):
        print(f"\n[+] Loading Indian Mutual Funds from: {os.path.basename(files['mf'])}")
        indian_mf = mf_parser.parse(files['mf'])
        indian_gains.append(indian_mf)
    elif files['mf']:
        print(f"\n[WARN] Indian Mutual Funds file not found: {files['mf']}")
    
    # Process Zerodha P&L file
    if files['zerodha'] and os.path.exists(files['zerodha']):
        print(f"\n[+] Loading Zerodha P&L from: {os.path.basename(files['zerodha'])}")
        zerodha_gains = zerodha_parser.parse(files['zerodha'])
        indian_gains.append(zerodha_gains)
    elif files['zerodha']:
        print(f"\n[WARN] Zerodha P&L file not found: {files['zerodha']}")
    
    # Check if we have any data
    if not all_transactions and not indian_gains:
        print("\n[ERROR] No sale transactions found in the specified date range.")
        return
    
    print(f"\n[*] Total combined sale transactions: {len(all_transactions)}")
    
    # Initialize services
    calculator = CapitalGainsCalculator()
    console_reporter = ConsoleReporter()
    excel_reporter = ExcelReporter()
    tax_calculator = TaxCalculator()
    
    # Calculate capital gains
    if all_transactions:
        all_transactions = calculator.calculate(
            all_transactions,
            use_sbi=True,
            sbi_rates_file=files['sbi_rates']
        )
        
        # Print reports
        console_reporter.print_detailed_report(all_transactions, "DETAILED CAPITAL GAINS REPORT")
        console_reporter.print_summary_report(all_transactions, "COMBINED CAPITAL GAINS SUMMARY")
    
    # Print grand total
    if all_transactions or indian_gains:
        console_reporter.print_grand_total(all_transactions, indian_gains)
    
    # Print quarterly breakdown
    if all_transactions:
        console_reporter.print_quarterly_breakdown(all_transactions, indian_gains)
    
    # Calculate taxes
    tax_data = tax_calculator.calculate(
        transactions=all_transactions,
        indian_gains=indian_gains,
        taxes_paid=args.taxes_paid
    )
    tax_calculator.print_calculation(tax_data)
    
    # Export to Excel
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    excel_path = os.path.join(script_dir, f"capital_gains_report_{timestamp}.xlsx")
    
    if all_transactions:
        excel_reporter.export(
            filepath=excel_path,
            transactions=all_transactions,
            exchange_rates=calculator.get_exchange_rates_cache(),
            indian_gains=indian_gains,
            tax_data=tax_data
        )
    
    # Save exchange rates cache
    rates_path = os.path.join(script_dir, "exchange_rates_cache.json")
    calculator.save_exchange_rates(rates_path)
    print(f"\n[+] Exchange rates saved to: {rates_path}")
    
    print("\n" + "=" * 80)
    print("  CALCULATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()

