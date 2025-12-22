#!/usr/bin/env python3
"""
Script to generate sbi_reference_rates.json from multiple sources.

Sources:
1. SBI FX RateKeeper (2020-present): https://github.com/sahilgupta/sbi-fx-ratekeeper
2. Perquisite emails (2017-present): Extracts RBI exchange rates from RSU/ESPP perquisite emails

Usage:
    python generate_sbi_rates.py                    # Update from all sources
    python generate_sbi_rates.py --sbi-only         # Only fetch SBI rates (2020+)
    python generate_sbi_rates.py --perquisites-only # Only extract from perquisite emails
"""

import argparse
import base64
import csv
import json
import os
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path


# SBI FX RateKeeper (2020-present)
SBI_CSV_URL = "https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/main/csv_files/SBI_REFERENCE_RATES_USD.csv"

# Paths
SCRIPT_DIR = Path(__file__).parent
OUTPUT_FILE = SCRIPT_DIR / "sbi_reference_rates.json"
PERQUISITES_DIR = SCRIPT_DIR / "perquisites"


def download_csv(url: str) -> str:
    """Download CSV content from URL."""
    print(f"[*] Downloading CSV from {url}...")
    with urllib.request.urlopen(url) as response:
        return response.read().decode("utf-8")


def parse_sbi_csv(csv_content: str) -> dict[str, float]:
    """
    Parse SBI FX RateKeeper CSV and extract date -> TT BUY rate mapping.
    Available from 2020 onwards.
    """
    rates = {}
    reader = csv.reader(StringIO(csv_content))
    
    # Skip header row
    header = next(reader)
    print(f"   CSV columns: {header[:4]}...")
    
    for row in reader:
        if len(row) < 3:
            continue
        
        # Extract date (YYYY-MM-DD) from datetime string
        date_str = row[0].split()[0]  # "2020-01-06 09:00" -> "2020-01-06"
        
        # Extract TT BUY rate
        try:
            tt_buy = float(row[2])
        except ValueError:
            continue
        
        # Skip zero rates
        if tt_buy == 0.0:
            continue
        
        rates[date_str] = tt_buy
    
    return rates


class TableDataExtractor(HTMLParser):
    """Extract table data from HTML, supporting multiple tables."""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_table = []
        self.tables = []  # List of all tables found
        self.current_data = ""
    
    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
            self.current_table = []
        elif tag == "tr" and self.in_table:
            self.in_row = True
            self.current_row = []
        elif tag == "td" and self.in_row:
            self.in_cell = True
            self.current_data = ""
    
    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
            if self.current_table:
                self.tables.append(self.current_table)
            self.current_table = []
        elif tag == "tr" and self.in_row:
            self.in_row = False
            if self.current_row:
                self.current_table.append(self.current_row)
        elif tag == "td" and self.in_cell:
            self.in_cell = False
            self.current_row.append(self.current_data.strip())
    
    def handle_data(self, data):
        if self.in_cell:
            self.current_data += data
    
    def get_data_table(self) -> list:
        """Return the largest table (most likely the data table)."""
        if not self.tables:
            return []
        # Find table with most columns (the data table)
        return max(self.tables, key=lambda t: max(len(row) for row in t) if t else 0)


def parse_date_flexible(date_str: str) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    date_str = date_str.strip()
    
    # Try different formats
    formats = [
        "%d-%b-%y",      # 21-Jun-23
        "%d-%b-%Y",      # 21-Jun-2023
        "%d-%m-%Y",      # 31-08-2023
        "%d/%m/%Y",      # 31/08/2023
        "%d-%m-%y",      # 31-08-23
        "%Y-%m-%d",      # 2023-08-31
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return None


def extract_rates_from_rsu_email(html_content: str) -> dict[str, float]:
    """
    Extract exchange rates from RSU perquisite email.
    
    RSU emails have columns including:
    - Transaction Date (column 4 in newer, varies in older)
    - RBI Exchange Rate (column 11 in newer, column 13 in older)
    """
    rates = {}
    
    parser = TableDataExtractor()
    parser.feed(html_content)
    
    rows = parser.get_data_table()
    if not rows:
        return rates
    
    # Find header row to determine column indices
    header_row = rows[0] if rows else []
    
    # Find transaction date and exchange rate columns by scanning header
    date_col = None
    rate_col = None
    
    for i, cell in enumerate(header_row):
        cell_lower = cell.lower().replace(" ", "")
        # Look for transaction date column
        if "transactiondate" in cell_lower or "4.transaction" in cell_lower:
            date_col = i
        # Look for RBI exchange rate column (various formats)
        if "rbiexchangerate" in cell_lower or "rbiexchange" in cell_lower:
            rate_col = i
        # Also check numbered columns like "11.RBI" or "13.RBI"
        if re.match(r'\d+\.rbi', cell_lower):
            rate_col = i
    
    # If header detection failed, try positional approach based on row length
    if date_col is None or rate_col is None:
        for row in rows[1:2]:  # Check first data row
            # RSU emails typically have Transaction Date at index 3 (0-based)
            # and RBI rate around index 10-12
            if len(row) >= 13:
                # Try common positions
                test_date_cols = [3, 4]
                test_rate_cols = [10, 11, 12, 13]
                
                for dc in test_date_cols:
                    if dc < len(row) and parse_date_flexible(row[dc]):
                        date_col = dc
                        break
                
                for rc in test_rate_cols:
                    if rc < len(row):
                        try:
                            val = float(row[rc].replace(",", ""))
                            if 40 <= val <= 100:
                                rate_col = rc
                                break
                        except:
                            pass
    
    # Extract rates from data rows
    for row in rows[1:]:  # Skip header
        if date_col is None or rate_col is None:
            continue
        if len(row) <= max(date_col, rate_col):
            continue
        
        try:
            date_str = parse_date_flexible(row[date_col])
            rate_str = row[rate_col].replace(",", "").strip()
            
            if date_str and rate_str and rate_str != "-":
                rate = float(rate_str)
                if 40 <= rate <= 100:  # Sanity check for USD/INR range
                    rates[date_str] = rate
        except (ValueError, IndexError):
            continue
    
    return rates


def extract_rates_from_espp_email(html_content: str) -> dict[str, float]:
    """
    Extract exchange rates from ESPP perquisite email.
    
    ESPP emails have columns including:
    - Purchase Date (column 7)
    - Exchange rate on Date of purchase (column 16)
    """
    rates = {}
    
    parser = TableDataExtractor()
    parser.feed(html_content)
    
    rows = parser.get_data_table()
    if not rows:
        return rates
    
    # Find header row
    header_row = rows[0] if rows else []
    
    # Find columns
    date_col = None
    rate_col = None
    
    for i, cell in enumerate(header_row):
        cell_lower = cell.lower().replace(" ", "")
        # Look for purchase date column
        if "purchasedate" in cell_lower or "7.purchase" in cell_lower:
            date_col = i
        # Look for exchange rate on purchase date (last column usually)
        if ("exchangerate" in cell_lower and "purchase" in cell_lower) or "16.exchange" in cell_lower:
            rate_col = i
    
    # If header detection failed, try positional approach
    if date_col is None or rate_col is None:
        for row in rows[1:2]:
            # ESPP: Purchase Date is typically around column 6, exchange rate at end
            if len(row) >= 16:
                test_date_cols = [6, 7]
                for dc in test_date_cols:
                    if dc < len(row) and parse_date_flexible(row[dc]):
                        date_col = dc
                        break
                
                # Exchange rate is typically the last column
                for rc in [15, 14, len(row) - 1]:
                    if rc < len(row):
                        try:
                            val = float(row[rc].replace(",", ""))
                            if 40 <= val <= 100:
                                rate_col = rc
                                break
                        except:
                            pass
    
    # Extract rates
    for row in rows[1:]:
        if date_col is None or rate_col is None:
            continue
        if len(row) <= max(date_col, rate_col):
            continue
        
        try:
            date_str = parse_date_flexible(row[date_col])
            rate_str = row[rate_col].replace(",", "").strip()
            
            if date_str and rate_str and rate_str != "-":
                rate = float(rate_str)
                if 40 <= rate <= 100:
                    rates[date_str] = rate
        except (ValueError, IndexError):
            continue
    
    return rates


def decode_eml_content(eml_path: Path) -> str | None:
    """Decode HTML content from .eml file."""
    with open(eml_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Parse line by line to find HTML base64 block
    lines = content.split('\n')
    in_html_section = False
    found_base64 = False
    base64_lines = []
    
    for line in lines:
        line_lower = line.lower()
        
        if 'content-type:' in line_lower and 'text/html' in line_lower:
            in_html_section = True
            found_base64 = False
            base64_lines = []
        elif in_html_section and 'content-transfer-encoding:' in line_lower and 'base64' in line_lower:
            found_base64 = True
        elif in_html_section and found_base64:
            # Check for boundary (end of section)
            if line.startswith('--'):
                break
            # Skip empty lines at the start
            stripped = line.strip()
            if stripped and not stripped.startswith('Content-'):
                base64_lines.append(stripped)
    
    if base64_lines:
        try:
            full_b64 = ''.join(base64_lines)
            decoded = base64.b64decode(full_b64).decode('utf-8')
            return decoded
        except Exception as e:
            print(f"   [!] Failed to decode {eml_path.name}: {e}")
    
    return None


def extract_rates_from_perquisites(perquisites_dir: Path) -> dict[str, float]:
    """Extract exchange rates from all perquisite emails."""
    rates = {}
    
    if not perquisites_dir.exists():
        print(f"[!] Perquisites directory not found: {perquisites_dir}")
        return rates
    
    eml_files = list(perquisites_dir.glob("*.eml"))
    print(f"[*] Found {len(eml_files)} perquisite email(s)")
    
    for eml_file in sorted(eml_files):
        html_content = decode_eml_content(eml_file)
        if not html_content:
            continue
        
        # Determine email type from filename
        filename = eml_file.name.upper()
        
        if "RSU" in filename:
            file_rates = extract_rates_from_rsu_email(html_content)
            rates.update(file_rates)
            if file_rates:
                print(f"   [+] {eml_file.name}: {len(file_rates)} rate(s)")
        elif "ESPP" in filename:
            file_rates = extract_rates_from_espp_email(html_content)
            rates.update(file_rates)
            if file_rates:
                print(f"   [+] {eml_file.name}: {len(file_rates)} rate(s)")
    
    return rates


def load_existing_rates(filepath: Path) -> dict[str, float]:
    """Load existing rates from JSON file."""
    if filepath.exists():
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = json.load(f)
                print(f"[*] Loaded {len(existing)} existing rate(s)")
                return existing
        except (json.JSONDecodeError, IOError) as e:
            print(f"   [!] Could not load existing file: {e}")
    return {}


def save_json(rates: dict[str, float], output_path: Path) -> None:
    """Save rates dictionary to JSON file with sorted keys."""
    sorted_rates = dict(sorted(rates.items()))
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sorted_rates, f, indent=2)
    
    print(f"[OK] Saved {len(sorted_rates)} rate(s) to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate SBI reference rates JSON from multiple sources."
    )
    parser.add_argument(
        "--sbi-only",
        action="store_true",
        help="Only fetch SBI rates (2020-present)"
    )
    parser.add_argument(
        "--perquisites-only",
        action="store_true",
        help="Only extract from perquisite emails"
    )
    parser.add_argument(
        "--no-preserve",
        action="store_true",
        help="Don't preserve existing rates (overwrite)"
    )
    args = parser.parse_args()
    
    all_rates = {}
    
    # Step 1: Load existing rates (unless --no-preserve)
    if not args.no_preserve:
        all_rates.update(load_existing_rates(OUTPUT_FILE))
    
    # Step 2: Extract from perquisite emails (historical rates)
    if not args.sbi_only:
        perquisite_rates = extract_rates_from_perquisites(PERQUISITES_DIR)
        # Perquisite rates are used as fallback (don't overwrite SBI rates)
        for date, rate in perquisite_rates.items():
            if date not in all_rates:
                all_rates[date] = rate
        print(f"   Total from perquisites: {len(perquisite_rates)} unique rate(s)")
    
    # Step 3: Fetch SBI rates (2020+) - these are most accurate
    if not args.perquisites_only:
        try:
            csv_content = download_csv(SBI_CSV_URL)
            sbi_rates = parse_sbi_csv(csv_content)
            # SBI rates take precedence
            all_rates.update(sbi_rates)
            print(f"   Total from SBI: {len(sbi_rates)} rate(s)")
        except Exception as e:
            print(f"   [!] Could not fetch SBI rates: {e}")
    
    # Save combined rates
    save_json(all_rates, OUTPUT_FILE)
    
    # Print summary
    if all_rates:
        dates = sorted(all_rates.keys())
        print(f"\n[*] Summary:")
        print(f"   Total rates: {len(all_rates)}")
        print(f"   Date range:  {dates[0]} to {dates[-1]}")
        
        # Count by year
        year_counts = {}
        for d in dates:
            year = d[:4]
            year_counts[year] = year_counts.get(year, 0) + 1
        
        print(f"   By year:")
        for year in sorted(year_counts.keys()):
            print(f"      {year}: {year_counts[year]} rate(s)")


if __name__ == "__main__":
    main()
