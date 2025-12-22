"""
Utility functions for the Capital Gains Calculator.

This module contains helper functions for parsing, file handling,
and other common operations.
"""

import glob
import os
from datetime import datetime
from typing import Optional


def parse_currency(value: str) -> float:
    """
    Parse currency string like '$123.45' to float.
    
    Args:
        value: Currency string (e.g., '$1,234.56', '-$100.00', '')
        
    Returns:
        Float value extracted from the string
        
    Examples:
        >>> parse_currency('$1,234.56')
        1234.56
        >>> parse_currency('-$100.00')
        100.0
        >>> parse_currency('')
        0.0
    """
    if not value or str(value).strip() == "":
        return 0.0
    return float(str(value).replace("$", "").replace(",", "").replace("-", ""))


def parse_date(date_str: str, date_format: str = "%m/%d/%Y") -> datetime:
    """
    Parse date string to datetime object.
    
    Args:
        date_str: Date string (e.g., '12/31/2024')
        date_format: Expected format (default: MM/DD/YYYY)
        
    Returns:
        datetime object
        
    Raises:
        ValueError: If date_str doesn't match the expected format
        
    Examples:
        >>> parse_date('12/31/2024')
        datetime(2024, 12, 31)
        >>> parse_date('2024-12-31', '%Y-%m-%d')
        datetime(2024, 12, 31)
    """
    return datetime.strptime(date_str, date_format)


def find_file_in_statements(pattern: str, statements_dir: str) -> Optional[str]:
    """
    Find a file matching pattern in the statements directory.
    
    Args:
        pattern: Glob pattern to match (e.g., 'EquityAwardsCenter_*.json')
        statements_dir: Path to the statements directory
        
    Returns:
        Path to the most recently modified matching file, or None if not found
        
    Examples:
        >>> find_file_in_statements('*.json', '/path/to/statements')
        '/path/to/statements/file.json'
    """
    search_pattern = os.path.join(statements_dir, pattern)
    matches = glob.glob(search_pattern)
    if matches:
        # Return the most recently modified file if multiple matches
        return max(matches, key=os.path.getmtime)
    return None


def format_currency_inr(amount: float, include_symbol: bool = True) -> str:
    """
    Format amount as Indian Rupees with proper comma separation.
    
    Args:
        amount: Amount to format
        include_symbol: Whether to include ₹ symbol
        
    Returns:
        Formatted string (e.g., '₹1,23,456.78')
        
    Examples:
        >>> format_currency_inr(123456.78)
        '₹1,23,456.78'
    """
    formatted = f"{amount:,.2f}"
    return f"₹{formatted}" if include_symbol else formatted


def format_currency_usd(amount: float, include_symbol: bool = True) -> str:
    """
    Format amount as US Dollars.
    
    Args:
        amount: Amount to format
        include_symbol: Whether to include $ symbol
        
    Returns:
        Formatted string (e.g., '$1,234.56')
    """
    formatted = f"{amount:,.2f}"
    return f"${formatted}" if include_symbol else formatted


def get_advance_tax_quarter(sale_date: datetime) -> str:
    """
    Get the advance tax quarter for a sale date.
    
    Indian advance tax quarters for FY (Apr-Mar):
    - Q1: Upto 15 Jun (Apr 1 - Jun 15)
    - Q2: 16 Jun - 15 Sep
    - Q3: 16 Sep - 15 Dec
    - Q4: 16 Dec - 15 Mar
    - Q5: 16 Mar - 31 Mar
    
    Args:
        sale_date: Date of the transaction
        
    Returns:
        Quarter name string
    """
    month = sale_date.month
    day = sale_date.day
    
    if month >= 4 and month <= 6:
        if month < 6 or (month == 6 and day <= 15):
            return "Upto 15 Jun"
        else:
            return "16 Jun-15 Sep"
    elif month >= 7 and month <= 9:
        if month < 9 or (month == 9 and day <= 15):
            return "16 Jun-15 Sep"
        else:
            return "16 Sep-15 Dec"
    elif month >= 10 and month <= 12:
        if month < 12 or (month == 12 and day <= 15):
            return "16 Sep-15 Dec"
        else:
            return "16 Dec-15 Mar"
    elif month >= 1 and month <= 3:
        if month < 3 or (month == 3 and day <= 15):
            return "16 Dec-15 Mar"
        else:
            return "16 Mar-31 Mar"
    
    return "Unknown"


# Constants for advance tax quarters
ADVANCE_TAX_QUARTERS = [
    "Upto 15 Jun",
    "16 Jun-15 Sep", 
    "16 Sep-15 Dec",
    "16 Dec-15 Mar",
    "16 Mar-31 Mar"
]

