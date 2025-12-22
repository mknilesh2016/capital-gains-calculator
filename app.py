"""
Capital Gains Calculator - Streamlit Web App

A web interface for calculating capital gains from stock sales,
designed for Indian residents with investments in both foreign (US) and Indian markets.
"""

import streamlit as st
import json
import io
import os
import csv
import re
import base64
import tempfile
import zipfile
from datetime import datetime
from typing import List, Tuple, Optional, Dict
from urllib.request import urlopen
from urllib.error import URLError
from html.parser import HTMLParser

# SBI FX RateKeeper CSV URL (source of truth for exchange rates)
SBI_CSV_URL = "https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/main/csv_files/SBI_REFERENCE_RATES_USD.csv"


# ============================================================================
# Perquisite Email Parsing (for historical rates before Jan 2020)
# ============================================================================

class TableDataExtractor(HTMLParser):
    """Extract table data from HTML, supporting multiple tables."""
    
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_row = False
        self.in_cell = False
        self.current_row = []
        self.current_table = []
        self.tables = []
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
        return max(self.tables, key=lambda t: max(len(row) for row in t) if t else 0)


def parse_date_flexible(date_str: str) -> Optional[str]:
    """Parse various date formats to YYYY-MM-DD."""
    date_str = date_str.strip()
    formats = [
        "%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", 
        "%d/%m/%Y", "%d-%m-%y", "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_rates_from_rsu_email(html_content: str) -> Dict[str, float]:
    """Extract exchange rates from RSU perquisite email."""
    rates = {}
    parser = TableDataExtractor()
    parser.feed(html_content)
    rows = parser.get_data_table()
    if not rows:
        return rates
    
    header_row = rows[0] if rows else []
    date_col = None
    rate_col = None
    
    for i, cell in enumerate(header_row):
        cell_lower = cell.lower().replace(" ", "")
        if "transactiondate" in cell_lower or "4.transaction" in cell_lower:
            date_col = i
        if "rbiexchangerate" in cell_lower or "rbiexchange" in cell_lower:
            rate_col = i
        if re.match(r'\d+\.rbi', cell_lower):
            rate_col = i
    
    if date_col is None or rate_col is None:
        for row in rows[1:2]:
            if len(row) >= 13:
                for dc in [3, 4]:
                    if dc < len(row) and parse_date_flexible(row[dc]):
                        date_col = dc
                        break
                for rc in [10, 11, 12, 13]:
                    if rc < len(row):
                        try:
                            val = float(row[rc].replace(",", ""))
                            if 40 <= val <= 100:
                                rate_col = rc
                                break
                        except:
                            pass
    
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


def extract_rates_from_espp_email(html_content: str) -> Dict[str, float]:
    """Extract exchange rates from ESPP perquisite email."""
    rates = {}
    parser = TableDataExtractor()
    parser.feed(html_content)
    rows = parser.get_data_table()
    if not rows:
        return rates
    
    header_row = rows[0] if rows else []
    date_col = None
    rate_col = None
    
    for i, cell in enumerate(header_row):
        cell_lower = cell.lower().replace(" ", "")
        if "purchasedate" in cell_lower or "7.purchase" in cell_lower:
            date_col = i
        if ("exchangerate" in cell_lower and "purchase" in cell_lower) or "16.exchange" in cell_lower:
            rate_col = i
    
    if date_col is None or rate_col is None:
        for row in rows[1:2]:
            if len(row) >= 16:
                for dc in [6, 7]:
                    if dc < len(row) and parse_date_flexible(row[dc]):
                        date_col = dc
                        break
                for rc in [15, 14, len(row) - 1]:
                    if rc < len(row):
                        try:
                            val = float(row[rc].replace(",", ""))
                            if 40 <= val <= 100:
                                rate_col = rc
                                break
                        except:
                            pass
    
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


def decode_eml_content(eml_content: str) -> Optional[str]:
    """Decode HTML content from .eml file content."""
    lines = eml_content.split('\n')
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
            if line.startswith('--'):
                break
            stripped = line.strip()
            if stripped and not stripped.startswith('Content-'):
                base64_lines.append(stripped)
    
    if base64_lines:
        try:
            full_b64 = ''.join(base64_lines)
            decoded = base64.b64decode(full_b64).decode('utf-8')
            return decoded
        except Exception:
            pass
    return None


def extract_rates_from_perquisite_zip(uploaded_zip) -> Dict[str, float]:
    """Extract exchange rates from a ZIP file containing perquisite emails (.eml)."""
    all_rates = {}
    processed_count = 0
    
    try:
        # Read the ZIP file
        zip_bytes = io.BytesIO(uploaded_zip.read())
        with zipfile.ZipFile(zip_bytes, 'r') as zf:
            # Process each .eml file in the ZIP
            for filename in zf.namelist():
                if not filename.lower().endswith('.eml'):
                    continue
                
                try:
                    # Read the .eml file content
                    with zf.open(filename) as eml_file:
                        content = eml_file.read().decode('utf-8', errors='ignore')
                    
                    html_content = decode_eml_content(content)
                    if not html_content:
                        continue
                    
                    # Determine email type from filename
                    filename_upper = filename.upper()
                    if "RSU" in filename_upper:
                        rates = extract_rates_from_rsu_email(html_content)
                        all_rates.update(rates)
                        if rates:
                            processed_count += 1
                    elif "ESPP" in filename_upper:
                        rates = extract_rates_from_espp_email(html_content)
                        all_rates.update(rates)
                        if rates:
                            processed_count += 1
                except Exception:
                    continue
    except zipfile.BadZipFile:
        st.error("Invalid ZIP file. Please upload a valid ZIP archive.")
    except Exception as e:
        st.error(f"Error processing ZIP file: {str(e)}")
    
    return all_rates

from capital_gains import (
    CapitalGainsCalculator,
    TaxCalculator,
    SaleTransaction,
    IndianGains,
    TaxData,
)
from capital_gains.parsers import (
    SchwabEACParser,
    SchwabIndividualParser,
    IndianStocksParser,
    IndianMutualFundsParser,
    ZerodhaPnLParser,
)
from capital_gains.reports import ExcelReporter
from capital_gains.utils import ADVANCE_TAX_QUARTERS, get_advance_tax_quarter

# Page configuration
st.set_page_config(
    page_title="Capital Gains Calculator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for beautiful styling
st.markdown("""
<style>
    /* Import Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    /* Main app styling */
    .stApp {
        font-family: 'DM Sans', sans-serif;
    }
    
    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        border: 1px solid rgba(255,255,255,0.1);
    }
    
    .main-header h1 {
        color: #e94560;
        font-size: 2.5rem;
        font-weight: 700;
        margin: 0;
        text-shadow: 0 2px 10px rgba(233, 69, 96, 0.3);
    }
    
    .main-header p {
        color: #a0a0a0;
        font-size: 1.1rem;
        margin: 0.5rem 0 0 0;
    }
    
    /* Card styling */
    .metric-card {
        background: linear-gradient(145deg, #1e1e2f 0%, #2a2a40 100%);
        padding: 1.5rem;
        border-radius: 12px;
        border: 1px solid rgba(233, 69, 96, 0.2);
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        margin-bottom: 1rem;
    }
    
    .metric-card h3 {
        color: #e94560;
        font-size: 0.9rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin: 0 0 0.5rem 0;
    }
    
    .metric-card .value {
        color: #ffffff;
        font-size: 1.8rem;
        font-weight: 700;
        font-family: 'JetBrains Mono', monospace;
    }
    
    .metric-card .subtext {
        color: #808080;
        font-size: 0.85rem;
        margin-top: 0.3rem;
    }
    
    /* Success card */
    .success-card {
        background: linear-gradient(145deg, #0d3320 0%, #1a4a30 100%);
        border: 1px solid rgba(46, 204, 113, 0.3);
    }
    
    .success-card h3 {
        color: #2ecc71;
    }
    
    /* Warning card */
    .warning-card {
        background: linear-gradient(145deg, #3d2e0a 0%, #4a3a10 100%);
        border: 1px solid rgba(241, 196, 15, 0.3);
    }
    
    .warning-card h3 {
        color: #f1c40f;
    }
    
    /* Table styling */
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.9rem;
        margin: 1rem 0;
    }
    
    .styled-table th {
        background: #1a1a2e;
        color: #e94560;
        padding: 1rem;
        text-align: left;
        font-weight: 600;
        border-bottom: 2px solid #e94560;
    }
    
    .styled-table td {
        padding: 0.8rem 1rem;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        color: #e0e0e0;
    }
    
    .styled-table tr:hover td {
        background: rgba(233, 69, 96, 0.1);
    }
    
    /* Sidebar styling */
    .css-1d391kg {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    
    /* File uploader */
    .stFileUploader {
        border: 2px dashed rgba(233, 69, 96, 0.4);
        border-radius: 12px;
        padding: 1rem;
        background: rgba(233, 69, 96, 0.05);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #e94560 0%, #c73e54 100%);
        color: white;
        border: none;
        padding: 0.75rem 2rem;
        border-radius: 8px;
        font-weight: 600;
        font-size: 1rem;
        box-shadow: 0 4px 15px rgba(233, 69, 96, 0.3);
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        box-shadow: 0 6px 25px rgba(233, 69, 96, 0.5);
        transform: translateY(-2px);
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(145deg, #0f3460 0%, #16213e 100%);
        border-left: 4px solid #e94560;
        padding: 1rem 1.5rem;
        border-radius: 0 8px 8px 0;
        margin: 1rem 0;
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: linear-gradient(145deg, #1e1e2f 0%, #2a2a40 100%);
        border-radius: 8px;
        font-weight: 600;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: rgba(233, 69, 96, 0.1);
        border-radius: 8px;
        padding: 0.5rem 1.5rem;
        color: #e94560;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #e94560 0%, #c73e54 100%);
        color: white;
    }
</style>
""", unsafe_allow_html=True)


def create_header():
    """Create the main header with disclaimer."""
    st.markdown("""
    <div class="main-header">
        <h1>📊 Capital Gains Calculator</h1>
        <p>Calculate capital gains for Indian tax filing • Supports Schwab, Groww & Zerodha</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Disclaimer
    st.markdown("""
    <div style="background: linear-gradient(145deg, #3d2e0a 0%, #4a3a10 100%); 
                border: 1px solid rgba(241, 196, 15, 0.3); 
                border-radius: 8px; 
                padding: 0.8rem 1rem; 
                margin-bottom: 1.5rem;
                font-size: 0.85rem;">
        <strong style="color: #f1c40f;">⚠️ Disclaimer:</strong>
        <span style="color: #d0d0d0;">
            This tool is for <strong>personal, non-commercial use only</strong>. 
            Calculations are provided as-is without any guarantee of correctness. 
            Always verify with a qualified tax professional before filing your returns.
        </span>
        <br><br>
        <strong style="color: #f1c40f;">📊 Tax Rate Assumption:</strong>
        <span style="color: #d0d0d0;">
            This calculator uses <strong>New Tax Regime</strong> with <strong>39% effective rate</strong> 
            (30% slab + 25% surcharge + 4% cess) for foreign STCG, assuming income above ₹2 Cr.
        </span>
    </div>
    """, unsafe_allow_html=True)


def create_metric_card(title: str, value: str, subtext: str = "", card_type: str = "default"):
    """Create a styled metric card."""
    card_class = "metric-card"
    if card_type == "success":
        card_class += " success-card"
    elif card_type == "warning":
        card_class += " warning-card"
    
    return f"""
    <div class="{card_class}">
        <h3>{title}</h3>
        <div class="value">{value}</div>
        {f'<div class="subtext">{subtext}</div>' if subtext else ''}
    </div>
    """


def format_inr(amount: float) -> str:
    """Format amount in Indian number format."""
    if amount >= 10000000:  # Crore
        return f"₹{amount/10000000:.2f} Cr"
    elif amount >= 100000:  # Lakh
        return f"₹{amount/100000:.2f} L"
    else:
        return f"₹{amount:,.2f}"


def format_inr_full(amount: float) -> str:
    """Format amount in full Indian number format."""
    return f"₹{amount:,.2f}"


def process_eac_file(uploaded_file, start_date: datetime) -> List[SaleTransaction]:
    """Process Schwab EAC transactions file."""
    try:
        content = json.load(uploaded_file)
        parser = SchwabEACParser()
        transactions = content.get("Transactions", [])
        return parser.parse(transactions, start_date)
    except Exception as e:
        st.error(f"Error processing EAC file: {str(e)}")
        return []


def process_individual_file(uploaded_file, start_date: datetime) -> List[SaleTransaction]:
    """Process Schwab Individual transactions file."""
    try:
        content = json.load(uploaded_file)
        parser = SchwabIndividualParser()
        transactions = content.get("BrokerageTransactions", [])
        return parser.parse(transactions, start_date)
    except Exception as e:
        st.error(f"Error processing Individual file: {str(e)}")
        return []


def _safe_delete_file(filepath: str) -> None:
    """Safely delete a file, ignoring errors if it doesn't exist."""
    try:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)
    except (OSError, IOError):
        pass  # Ignore deletion errors


def process_indian_stocks_file(uploaded_file) -> Optional[IndianGains]:
    """Process Indian stocks file. Ensures temp file is deleted after use."""
    tmp_path = None
    try:
        # Save to temp file for openpyxl
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        parser = IndianStocksParser()
        result = parser.parse(tmp_path)
        return result
    except Exception as e:
        st.error(f"Error processing Indian Stocks file: {str(e)}")
        return None
    finally:
        _safe_delete_file(tmp_path)


def process_indian_mf_file(uploaded_file) -> Optional[IndianGains]:
    """Process Indian mutual funds file. Ensures temp file is deleted after use."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        parser = IndianMutualFundsParser()
        result = parser.parse(tmp_path)
        return result
    except Exception as e:
        st.error(f"Error processing Mutual Funds file: {str(e)}")
        return None
    finally:
        _safe_delete_file(tmp_path)


def process_zerodha_pnl_file(uploaded_file) -> Optional[IndianGains]:
    """Process Zerodha P&L report file. Ensures temp file is deleted after use."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        
        parser = ZerodhaPnLParser()
        result = parser.parse(tmp_path)
        return result
    except Exception as e:
        st.error(f"Error processing Zerodha P&L file: {str(e)}")
        return None
    finally:
        _safe_delete_file(tmp_path)


def load_sbi_rates_from_file(uploaded_file) -> Optional[dict]:
    """Load SBI rates from uploaded JSON file."""
    try:
        return json.load(uploaded_file)
    except Exception as e:
        st.error(f"Error loading SBI rates file: {str(e)}")
        return None


@st.cache_data(ttl=3600, show_spinner=False)  # Cache for 1 hour
def fetch_sbi_rates() -> Optional[dict]:
    """
    Fetch SBI TT Buy rates from SBI FX RateKeeper.
    Uses the same source as generate_sbi_rates.py.
    Note: Only available from January 2020 onwards.
    """
    try:
        with urlopen(SBI_CSV_URL, timeout=15) as response:
            csv_content = response.read().decode("utf-8")
        
        rates = {}
        reader = csv.reader(io.StringIO(csv_content))
        
        # Skip header row
        next(reader)
        
        for row in reader:
            if len(row) < 3:
                continue
            
            # Extract date (YYYY-MM-DD) from datetime string
            date_str = row[0].split()[0]  # "2020-01-06 09:00" -> "2020-01-06"
            
            # Extract TT BUY rate (column 2)
            try:
                tt_buy = float(row[2])
            except ValueError:
                continue
            
            # Skip zero rates
            if tt_buy == 0.0:
                continue
            
            rates[date_str] = tt_buy
        
        return rates
    except URLError as e:
        st.warning(f"Could not fetch SBI rates: {str(e)}")
        return None
    except Exception as e:
        st.warning(f"Error parsing SBI rates: {str(e)}")
        return None


def display_transaction_summary(transactions: List[SaleTransaction]):
    """Display transaction summary metrics."""
    if not transactions:
        return
    
    long_term = [t for t in transactions if t.is_long_term]
    short_term = [t for t in transactions if not t.is_long_term]
    
    ltcg = sum(t.capital_gain_inr for t in long_term)
    stcg = sum(t.capital_gain_inr for t in short_term)
    total = ltcg + stcg
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(create_metric_card(
            "Total Transactions",
            str(len(transactions)),
            f"{len(long_term)} LTCG • {len(short_term)} STCG"
        ), unsafe_allow_html=True)
    
    with col2:
        st.markdown(create_metric_card(
            "Long Term Gains",
            format_inr(ltcg),
            f"{len(long_term)} transactions",
            "success" if ltcg >= 0 else "warning"
        ), unsafe_allow_html=True)
    
    with col3:
        st.markdown(create_metric_card(
            "Short Term Gains",
            format_inr(stcg),
            f"{len(short_term)} transactions",
            "success" if stcg >= 0 else "warning"
        ), unsafe_allow_html=True)
    
    with col4:
        st.markdown(create_metric_card(
            "Total Capital Gains",
            format_inr(total),
            "From foreign stocks",
            "success" if total >= 0 else "warning"
        ), unsafe_allow_html=True)


def display_indian_gains_summary(indian_gains: List[IndianGains]):
    """Display Indian gains summary."""
    if not indian_gains:
        return
    
    total_ltcg = sum(g.ltcg for g in indian_gains)
    total_stcg = sum(g.stcg for g in indian_gains)
    
    st.markdown("### 🇮🇳 Indian Market Gains")
    
    cols = st.columns(len(indian_gains) + 1)
    
    for i, gain in enumerate(indian_gains):
        with cols[i]:
            st.markdown(create_metric_card(
                gain.source,
                format_inr(gain.ltcg + gain.stcg),
                f"LTCG: {format_inr(gain.ltcg)} • STCG: {format_inr(gain.stcg)}"
            ), unsafe_allow_html=True)
    
    with cols[-1]:
        st.markdown(create_metric_card(
            "Total Indian Gains",
            format_inr(total_ltcg + total_stcg),
            f"LTCG: {format_inr(total_ltcg)} • STCG: {format_inr(total_stcg)}",
            "success"
        ), unsafe_allow_html=True)


def display_tax_summary(tax_data: TaxData):
    """Display tax calculation summary."""
    st.markdown("### 💰 Tax Calculation")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(create_metric_card(
            "LTCG Tax",
            format_inr(tax_data.ltcg_tax),
            f"Foreign: {format_inr(tax_data.foreign_ltcg_tax)} + Indian: {format_inr(tax_data.indian_ltcg_tax)}"
        ), unsafe_allow_html=True)
    
    with col2:
        st.markdown(create_metric_card(
            "STCG Tax",
            format_inr(tax_data.stcg_tax),
            f"Foreign: {format_inr(tax_data.foreign_stcg_tax)} + Indian: {format_inr(tax_data.indian_stcg_tax)}"
        ), unsafe_allow_html=True)
    
    with col3:
        if tax_data.taxes_paid > 0:
            card_type = "warning" if tax_data.tax_liability > 0 else "success"
            st.markdown(create_metric_card(
                "Balance Tax Due",
                format_inr(tax_data.tax_liability),
                f"Total: {format_inr(tax_data.total_tax)} | Paid: {format_inr(tax_data.taxes_paid)}",
                card_type
            ), unsafe_allow_html=True)
        else:
            st.markdown(create_metric_card(
                "Total Tax Payable",
                format_inr(tax_data.total_tax),
                "Includes surcharge & cess"
            ), unsafe_allow_html=True)


def display_detailed_transactions(transactions: List[SaleTransaction]):
    """Display detailed transaction table."""
    if not transactions:
        return
    
    sorted_txns = sorted(transactions, key=lambda x: (x.sale_date, x.symbol))
    
    table_data = []
    for txn in sorted_txns:
        table_data.append({
            "Sale Date": txn.sale_date.strftime("%d-%b-%Y"),
            "Symbol": txn.symbol,
            "Type": txn.stock_type,
            "Shares": f"{txn.shares:.3f}" if txn.shares != int(txn.shares) else int(txn.shares),
            "Sale Price (₹)": format_inr_full(txn.sale_price_inr),
            "Acq. Price (₹)": format_inr_full(txn.acquisition_price_inr),
            "Capital Gain (₹)": format_inr_full(txn.capital_gain_inr),
            "Term": "LTCG" if txn.is_long_term else "STCG",
            "Days Held": txn.holding_period_days,
        })
    
    import pandas as pd
    df = pd.DataFrame(table_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def display_quarterly_breakdown(transactions: List[SaleTransaction], indian_gains: List[IndianGains]):
    """Display quarterly breakdown for advance tax."""
    if not transactions and not indian_gains:
        return
    
    st.markdown("### 📅 Quarterly Breakdown (Advance Tax)")
    
    quarters = ADVANCE_TAX_QUARTERS
    
    # Calculate foreign quarterly data
    foreign_data = {q: {"ltcg": 0, "stcg": 0} for q in quarters}
    for txn in transactions:
        quarter = get_advance_tax_quarter(txn.sale_date)
        if quarter in foreign_data:
            if txn.is_long_term:
                foreign_data[quarter]["ltcg"] += txn.capital_gain_inr
            else:
                foreign_data[quarter]["stcg"] += txn.capital_gain_inr
    
    # Create quarterly table
    import pandas as pd
    
    data = []
    for q in quarters:
        ltcg = foreign_data[q]["ltcg"]
        stcg = foreign_data[q]["stcg"]
        data.append({
            "Quarter": q,
            "LTCG": format_inr_full(ltcg),
            "STCG": format_inr_full(stcg),
            "Total": format_inr_full(ltcg + stcg),
        })
    
    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def generate_excel_report(
    transactions: List[SaleTransaction],
    indian_gains: List[IndianGains],
    tax_data: TaxData,
    exchange_rates: dict
) -> bytes:
    """Generate Excel report and return as bytes. Ensures temp file is deleted after use."""
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
            tmp_path = tmp.name
        
        reporter = ExcelReporter()
        reporter.export(
            filepath=tmp_path,
            transactions=transactions,
            exchange_rates=exchange_rates,
            indian_gains=indian_gains,
            tax_data=tax_data
        )
        
        with open(tmp_path, 'rb') as f:
            data = f.read()
        
        return data
    finally:
        _safe_delete_file(tmp_path)


def show_eula():
    """Display EULA acceptance dialog."""
    # Header
    st.markdown("""
    <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
                padding: 2rem 2.5rem;
                border-radius: 16px;
                margin-bottom: 2rem;
                box-shadow: 0 10px 40px rgba(0,0,0,0.3);
                border: 1px solid rgba(255,255,255,0.1);">
        <h1 style="color: #e94560; font-size: 2rem; margin: 0 0 1rem 0;">📜 End User License Agreement</h1>
        <p style="color: #a0a0a0; font-size: 1rem;">
            Please read and accept the following terms before using the Capital Gains Calculator.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Terms of Use - using native Streamlit markdown for better rendering
    st.markdown("### 📋 Terms of Use")
    
    st.markdown("""
**1. Non-Commercial Use Only**  
This tool is provided exclusively for **personal, non-commercial use**. 
You may not use this software for commercial purposes, redistribute it for profit, 
or incorporate it into commercial products or services.

**2. No Warranty or Guarantee**  
This calculator is provided **"AS IS" without any warranty of any kind**, 
either express or implied. The calculations are provided for informational purposes only 
and may contain errors, inaccuracies, or omissions. The developers make no representations 
or warranties regarding the accuracy, completeness, or reliability of any calculations.

**3. Not Professional Tax Advice**  
This tool does **NOT constitute professional tax, financial, or legal advice**. 
The output should not be solely relied upon for tax filing or any financial decisions. 
Always verify all calculations with a qualified Chartered Accountant (CA) or tax professional 
before filing your tax returns.

**4. Tax Rate Assumptions**  
This calculator uses the **New Tax Regime** with a **39% effective rate** 
(30% slab + 25% surcharge + 4% cess) for foreign STCG, assuming taxable income above ₹2 Crore. 
Your actual tax rates may differ based on your specific income and circumstances.

**5. Limitation of Liability**  
Under no circumstances shall the developers be liable for any direct, indirect, incidental, 
special, consequential, or punitive damages arising from the use of this calculator, 
including but not limited to any errors in tax calculations, missed deadlines, penalties, 
or interest charges from tax authorities.

**6. User Responsibility**  
You are solely responsible for verifying all calculations and ensuring compliance with 
applicable tax laws. By using this tool, you acknowledge that you understand these limitations 
and accept full responsibility for any decisions made based on the calculator's output.
""")
    
    # Privacy notice
    st.success("""
🔒 **Privacy Notice**  
Your files are processed entirely in your browser's memory and are **never uploaded 
or stored on any server**. All temporary files created during processing are 
automatically deleted immediately after use. No personal or financial data is retained 
or transmitted anywhere.
""")
    
    # Acceptance checkbox and button
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        accept_terms = st.checkbox(
            "I have read and agree to the above terms and conditions",
            key="eula_checkbox"
        )
        
        if st.button("✅ Accept & Continue", type="primary", use_container_width=True, disabled=not accept_terms):
            st.session_state['eula_accepted'] = True
            st.rerun()
        
        if not accept_terms:
            st.caption("⚠️ You must accept the terms to use this calculator")


def main():
    """Main application entry point."""
    # Check if EULA has been accepted
    if not st.session_state.get('eula_accepted', False):
        show_eula()
        return
    
    create_header()
    
    # Sidebar for file uploads and configuration
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        
        # Start date selection
        start_date = st.date_input(
            "Financial Year Start Date",
            value=datetime(2025, 4, 1),
            help="Start date for capital gains calculation"
        )
        start_date = datetime.combine(start_date, datetime.min.time())
        
        # Taxes already paid
        taxes_paid = st.number_input(
            "Taxes Already Paid (₹)",
            min_value=0.0,
            value=0.0,
            step=10000.0,
            help="Advance tax already paid for this FY"
        )
        
        st.markdown("---")
        st.markdown("## 📁 Upload Files")
        
        # File uploaders
        st.markdown("### Schwab Files")
        eac_file = st.file_uploader(
            "EAC Transactions (JSON)",
            type=['json'],
            help="Export from Schwab Equity Awards Center"
        )
        
        individual_file = st.file_uploader(
            "Individual Brokerage (JSON)",
            type=['json'],
            help="Export from Schwab Individual Brokerage"
        )
        
        st.markdown("### Indian Broker Files")
        stocks_file = st.file_uploader(
            "Groww Stocks Capital Gains (XLSX)",
            type=['xlsx'],
            help="Groww stocks capital gains report"
        )
        
        mf_file = st.file_uploader(
            "Groww Mutual Funds Capital Gains (XLSX)",
            type=['xlsx'],
            help="Groww mutual funds capital gains report"
        )
        
        zerodha_file = st.file_uploader(
            "Zerodha P&L Report (XLSX)",
            type=['xlsx'],
            help="Zerodha equity P&L report (pnl-*.xlsx)"
        )
        
        st.markdown("### Exchange Rates (Optional)")
        
        # Option 1: Upload ZIP of perquisite emails for historical rates
        perquisite_zip = st.file_uploader(
            "Perquisite Emails ZIP",
            type=['zip'],
            help="Upload a ZIP file containing RSU/ESPP perquisite emails (.eml) for pre-2020 rates"
        )
        
        # Option 2: Upload custom JSON rates file
        sbi_rates_file = st.file_uploader(
            "Or: Custom Rates JSON",
            type=['json'],
            help="Upload a complete sbi_reference_rates.json file"
        )
        
        st.markdown("""
        <div style="background: rgba(241, 196, 15, 0.1); 
                    border: 1px solid rgba(241, 196, 15, 0.3); 
                    border-radius: 6px; 
                    padding: 0.6rem; 
                    font-size: 0.75rem;
                    margin-top: 0.5rem;">
            <strong style="color: #f1c40f;">📅 Note:</strong>
            <span style="color: #c0c0c0;">
                Auto-fetched rates are available from <strong>January 2020</strong> onwards.<br>
                For older transactions, either:<br>
                • Upload a <strong>ZIP file</strong> containing RSU/ESPP perquisite emails (.eml), OR<br>
                • Upload a custom <code>sbi_reference_rates.json</code> file
            </span>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        calculate_btn = st.button("🧮 Calculate Gains", type="primary", use_container_width=True)
        
        # Clear data button
        if st.button("🗑️ Clear All Data", use_container_width=True):
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        # Privacy notice
        st.markdown("""
        <div style="background: rgba(46, 204, 113, 0.1); 
                    border: 1px solid rgba(46, 204, 113, 0.3); 
                    border-radius: 6px; 
                    padding: 0.6rem; 
                    font-size: 0.7rem;
                    margin-top: 0.5rem;">
            <strong style="color: #2ecc71;">🔒 Privacy:</strong>
            <span style="color: #c0c0c0;">
                Your files are processed in memory and <strong>not stored</strong> on any server. 
                All temporary files are automatically deleted after processing. 
                Click "Clear All Data" to remove any cached results.
            </span>
        </div>
        """, unsafe_allow_html=True)
    
    # Main content area
    if calculate_btn:
        with st.spinner("Processing transactions..."):
            all_transactions = []
            indian_gains = []
            sbi_rates = None
            
            # Load exchange rates from multiple sources
            sbi_rates = {}
            
            # Step 1: Extract rates from perquisite emails ZIP (historical rates pre-2020)
            if perquisite_zip:
                with st.spinner("📧 Extracting rates from perquisite emails..."):
                    perquisite_rates = extract_rates_from_perquisite_zip(perquisite_zip)
                if perquisite_rates:
                    sbi_rates.update(perquisite_rates)
                    st.success(f"✓ Extracted {len(perquisite_rates)} rates from perquisite emails")
            
            # Step 2: Load rates from JSON file OR fetch from SBI
            if sbi_rates_file:
                sbi_rates_file.seek(0)
                json_rates = load_sbi_rates_from_file(sbi_rates_file)
                if json_rates:
                    sbi_rates.update(json_rates)  # JSON rates override perquisite rates
                    st.success(f"✓ Loaded {len(json_rates)} rates from uploaded JSON")
            else:
                with st.spinner("📡 Fetching SBI TT Buy rates (Jan 2020 onwards)..."):
                    fetched_rates = fetch_sbi_rates()
                if fetched_rates:
                    sbi_rates.update(fetched_rates)  # SBI rates override perquisite rates
                    st.success(f"✓ Fetched {len(fetched_rates)} SBI exchange rates")
            
            if sbi_rates:
                st.info(f"📊 Total exchange rates available: {len(sbi_rates)}")
            
            # Process EAC file
            if eac_file:
                eac_file.seek(0)
                eac_txns = process_eac_file(eac_file, start_date)
                if eac_txns:
                    st.success(f"✓ Loaded {len(eac_txns)} EAC transactions")
                    all_transactions.extend(eac_txns)
            
            # Process Individual file
            if individual_file:
                individual_file.seek(0)
                ind_txns = process_individual_file(individual_file, start_date)
                if ind_txns:
                    st.success(f"✓ Loaded {len(ind_txns)} Individual transactions")
                    all_transactions.extend(ind_txns)
            
            # Process Indian stocks
            if stocks_file:
                stocks_file.seek(0)
                stocks_gains = process_indian_stocks_file(stocks_file)
                if stocks_gains:
                    st.success(f"✓ Loaded Indian Stocks gains")
                    indian_gains.append(stocks_gains)
            
            # Process Mutual Funds
            if mf_file:
                mf_file.seek(0)
                mf_gains = process_indian_mf_file(mf_file)
                if mf_gains:
                    st.success(f"✓ Loaded Mutual Funds gains")
                    indian_gains.append(mf_gains)
            
            # Process Zerodha P&L
            if zerodha_file:
                zerodha_file.seek(0)
                zerodha_gains = process_zerodha_pnl_file(zerodha_file)
                if zerodha_gains:
                    st.success(f"✓ Loaded Zerodha P&L gains")
                    indian_gains.append(zerodha_gains)
            
            if not all_transactions and not indian_gains:
                st.warning("No transactions found. Please upload at least one file.")
                return
            
            # Calculate capital gains
            calculator = CapitalGainsCalculator()
            if all_transactions:
                # Create temp file for SBI rates if provided
                sbi_rates_path = None
                try:
                    if sbi_rates:
                        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp:
                            json.dump(sbi_rates, tmp)
                            sbi_rates_path = tmp.name
                    
                    all_transactions = calculator.calculate(
                        all_transactions,
                        use_sbi=bool(sbi_rates),
                        sbi_rates_file=sbi_rates_path
                    )
                finally:
                    _safe_delete_file(sbi_rates_path)
            
            # Calculate taxes
            tax_calculator = TaxCalculator()
            tax_data = tax_calculator.calculate(
                transactions=all_transactions,
                indian_gains=indian_gains,
                taxes_paid=taxes_paid
            )
            
            # Store in session state for download
            st.session_state['transactions'] = all_transactions
            st.session_state['indian_gains'] = indian_gains
            st.session_state['tax_data'] = tax_data
            st.session_state['exchange_rates'] = calculator.get_exchange_rates_cache()
            st.session_state['calculated'] = True
    
    # Display results if calculated
    if st.session_state.get('calculated', False):
        transactions = st.session_state['transactions']
        indian_gains = st.session_state['indian_gains']
        tax_data = st.session_state['tax_data']
        exchange_rates = st.session_state['exchange_rates']
        
        st.markdown("---")
        
        # Summary metrics
        if transactions:
            st.markdown("### 🌍 Foreign Stock Gains (Schwab)")
            display_transaction_summary(transactions)
        
        display_indian_gains_summary(indian_gains)
        display_tax_summary(tax_data)
        
        st.markdown("---")
        
        # Tabs for detailed views
        tab1, tab2, tab3 = st.tabs(["📋 Transactions", "📅 Quarterly", "📊 Tax Details"])
        
        with tab1:
            if transactions:
                display_detailed_transactions(transactions)
            else:
                st.info("No foreign stock transactions to display.")
        
        with tab2:
            display_quarterly_breakdown(transactions, indian_gains)
        
        with tab3:
            st.markdown("#### Tax Breakdown")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Foreign Stocks (Schwab):**")
                st.write(f"- LTCG: {format_inr_full(tax_data.schwab_ltcg)}")
                st.write(f"- STCG: {format_inr_full(tax_data.schwab_stcg)}")
                
                if indian_gains:
                    st.markdown("**Indian Investments:**")
                    st.write(f"- LTCG: {format_inr_full(tax_data.indian_ltcg)}")
                    st.write(f"- STCG: {format_inr_full(tax_data.indian_stcg)}")
                    if tax_data.rebate_used > 0:
                        st.write(f"- LTCG Exemption Used: {format_inr_full(tax_data.rebate_used)}")
            
            with col2:
                st.markdown("**Tax Computation:**")
                st.write(f"- Foreign LTCG Tax: {format_inr_full(tax_data.foreign_ltcg_tax)}")
                st.write(f"- Foreign STCG Tax: {format_inr_full(tax_data.foreign_stcg_tax)}")
                st.write(f"- Indian LTCG Tax: {format_inr_full(tax_data.indian_ltcg_tax)}")
                st.write(f"- Indian STCG Tax: {format_inr_full(tax_data.indian_stcg_tax)}")
                st.write(f"- **Total Tax: {format_inr_full(tax_data.total_tax)}**")
        
        st.markdown("---")
        
        # Download Excel Report
        st.markdown("### 📥 Download Report")
        
        if st.button("📄 Generate Excel Report", type="secondary"):
            with st.spinner("Generating report..."):
                excel_data = generate_excel_report(
                    transactions,
                    indian_gains,
                    tax_data,
                    exchange_rates
                )
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    label="⬇️ Download Excel Report",
                    data=excel_data,
                    file_name=f"capital_gains_report_{timestamp}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
    
    else:
        # Instructions when no calculation done
        st.markdown("""
        <div class="info-box">
            <h3 style="color: #e94560; margin: 0 0 0.5rem 0;">Getting Started</h3>
            <ol style="color: #c0c0c0; margin: 0; padding-left: 1.5rem;">
                <li>Upload your transaction files using the sidebar</li>
                <li>Configure the financial year start date</li>
                <li>Enter any taxes already paid (optional)</li>
                <li>Click <strong>Calculate Gains</strong> to process</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("### 📚 Supported File Formats")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            **Schwab Files (JSON)**
            - EAC Transactions export
            - Individual Brokerage export
            
            *Export from Schwab History → JSON format*
            """)
        
        with col2:
            st.markdown("""
            **Indian Broker Files (XLSX)**
            - Groww Capital Gains Report
            - Groww Mutual Funds Report
            - Zerodha P&L Report
            
            *Download from your broker's tax reports section*
            """)
        
        with col3:
            st.markdown("""
            **Perquisite Emails (ZIP)**
            - ZIP containing .eml files
            - RSU/ESPP Perquisite Details
            
            *For historical rates (pre-2020) from payroll provider*
            """)
    
    # Footer disclaimer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #808080; font-size: 0.8rem; padding: 1rem 0;">
        <p style="margin: 0;">
            <strong>⚠️ Non-Commercial Use Only</strong><br>
            This calculator is provided for personal use without any warranty. 
            Calculations may contain errors and should not be relied upon for tax filing without professional verification.<br>
            <em>Always consult a qualified Chartered Accountant before filing your tax returns.</em>
        </p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()

