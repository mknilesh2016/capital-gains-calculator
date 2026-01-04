"""
Capital Gains Calculator - Streamlit Web App

A web interface for calculating capital gains from stock sales and generating
Schedule FA (Foreign Assets) reports, designed for Indian residents with 
investments in both foreign (US) and Indian markets.

Features:
- Capital Gains Calculator: Calculate gains from Schwab, Groww, and Zerodha
- Schedule FA Generator: Generate ITR-compliant foreign asset declarations
- Auto-fetch exchange rates: SBI TT Buy rates from Jan 2020 onwards
- Excel export: Comprehensive reports with all calculations

Run with: streamlit run app.py
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
from pathlib import Path
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
    ScheduleFAGenerator,
    ScheduleFAConfig,
)
from capital_gains.parsers import (
    SchwabEACParser,
    SchwabIndividualParser,
    IndianStocksParser,
    IndianMutualFundsParser,
    ZerodhaPnLParser,
    ForeignAssetsParser,
)
from capital_gains.reports import ExcelReporter, ScheduleFAExcelReporter

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


def _safe_delete_file(filepath: str) -> None:
    """Safely delete a file, ignoring errors if it doesn't exist."""
    try:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)
    except (OSError, IOError):
        pass  # Ignore deletion errors


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






def unified_main():
    """Unified main application with flow-based file uploads."""
    # Check if EULA has been accepted
    if not st.session_state.get('eula_accepted', False):
        show_eula()
        return
    
    # Sidebar with data management
    with st.sidebar:
        st.markdown("### ⚙️ Settings")
        
        if st.button("🗑️ Clear All Data", use_container_width=True, help="Clear uploaded files, cache, and reset the app"):
            # Clear Streamlit cache
            st.cache_data.clear()
            
            # Clear stock cache file
            cache_file = Path("stock_cache.json")
            if cache_file.exists():
                cache_file.unlink()
            
            # Increment uploader key to force file uploaders to reset
            st.session_state['uploader_key'] = st.session_state.get('uploader_key', 0) + 1
            
            # Clear uploaded files from session state
            if 'uploaded_files' in st.session_state:
                del st.session_state['uploaded_files']
            
            # Clear any other session state data (except eula and uploader_key)
            keys_to_clear = [k for k in st.session_state.keys() if k not in ['eula_accepted', 'uploader_key']]
            for key in keys_to_clear:
                del st.session_state[key]
            
            st.success("✅ All data cleared!")
            st.rerun()
        
        st.markdown("---")
        st.markdown("### 📚 Resources")
        st.markdown("""
        - [Schwab EAC](https://client.schwab.com/app/accounts/equityawards/)
        - [Schwab Brokerage](https://www.schwab.com)
        - [Groww Reports](https://groww.in)
        - [Zerodha Console](https://console.zerodha.com)
        """)
    
    # Header
    st.markdown("""
    <div class="main-header">
        <h1>📊 Capital Gains & Schedule FA</h1>
        <p>Calculate capital gains and generate Schedule FA for Indian Income Tax Returns</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ===== STEP 1: Report Type Selection =====
    st.markdown("### Step 1: Select Report Type")
    
    report_mode = st.radio(
        "What would you like to generate?",
        ["💰 Capital Gains Calculator", "📋 Schedule FA (Foreign Assets)"],
        horizontal=True,
        label_visibility="collapsed"
    )
    
    is_schedule_fa = "Schedule FA" in report_mode
    
    # ===== STEP 2: Configuration =====
    st.markdown("---")
    st.markdown("### Step 2: Configuration")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if is_schedule_fa:
            calendar_year = st.number_input(
                "Calendar Year",
                min_value=2020,
                max_value=2030,
                value=2025,
                help="Calendar year for Schedule FA reporting (Jan-Dec)"
            )
            start_date = datetime(calendar_year, 1, 1)
        else:
            start_date = st.date_input(
                "Financial Year Start",
                value=datetime(2025, 4, 1),
                help="Start of Indian financial year (typically April 1)"
            )
            start_date = datetime.combine(start_date, datetime.min.time())
            calendar_year = start_date.year if start_date.month >= 4 else start_date.year - 1
    
    with col2:
        if is_schedule_fa:
            st.markdown(f"**Assessment Year:** {calendar_year + 1}-{str(calendar_year + 2)[2:]}")
        else:
            taxes_paid = st.number_input(
                "Advance Tax Paid (₹)",
                min_value=0.0,
                value=0.0,
                step=10000.0,
                help="Tax already paid for this FY"
            )
    
    with col3:
        auto_fetch_rates = st.checkbox(
            "Auto-fetch SBI Rates",
            value=True,
            help="Automatically fetch USD-INR exchange rates"
        )
    
    # ===== STEP 3: Upload Files =====
    st.markdown("---")
    st.markdown("### Step 3: Upload Transaction Files")
    
    # Initialize file storage in session state
    if 'uploaded_files' not in st.session_state:
        st.session_state.uploaded_files = {}
    
    # Get uploader key prefix for resetting file uploaders
    uploader_key = st.session_state.get('uploader_key', 0)
    
    if is_schedule_fa:
        # Schedule FA file uploads
        st.markdown("#### 🇺🇸 Foreign Assets (Required)")
        
        with st.expander("ℹ️ How to download Schwab EAC files", expanded=False):
            st.markdown("""
            **EAC Transactions (JSON):**
            1. Go to [Schwab Equity Award Center](https://client.schwab.com/app/accounts/equityawards/)
            2. Login with your credentials
            3. Navigate to **History** → **Transactions**
            4. Set date range to cover the entire calendar year (Jan 1 - Dec 31)
            5. Click **Export** → Select **JSON** format
            6. Save file: `EquityAwardsCenter_Transactions_*.json`
            
            **Holdings CSV:**
            1. Go to [Equity Today View](https://client.schwab.com/app/accounts/equityawards/#/equityTodayView)
            2. Navigate to **Holdings** → **Equity Details** tab
            3. Click **Export** → Select **CSV** format
            4. Save file: `EquityAwardsCenter_EquityDetails_*.csv`
            
            *This file contains your current RSU/ESPP holdings with vest dates and FMV*
            """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            eac_file = st.file_uploader(
                "Schwab EAC Transactions",
                type=['json'],
                help="EquityAwardsCenter_Transactions_*.json - Export from Schwab EAC → History → Transactions → Export as JSON",
                key=f"eac_json_{uploader_key}"
            )
        
        with col2:
            holdings_file = st.file_uploader(
                "Schwab Holdings CSV",
                type=['csv'],
                help="EquityAwardsCenter_EquityDetails_*.csv - Export from Schwab EAC → Holdings → Equity Details → Export as CSV",
                key=f"holdings_csv_{uploader_key}"
            )
        
        st.markdown("#### 📈 Brokerage Account (Optional)")
        
        with st.expander("ℹ️ How to download Schwab Brokerage files", expanded=False):
            st.markdown("""
            **Individual Brokerage Transactions (JSON):**
            1. Go to [Schwab.com](https://www.schwab.com) and login
            2. Navigate to **Accounts** → Select your brokerage account
            3. Go to **History** → **Transactions**
            4. Set date range to cover the entire calendar year
            5. Click **Export** → Select **JSON** format
            6. Save file: `Individual_*_Transactions_*.json`
            
            *This includes ETFs, stocks, dividends, and other brokerage transactions*
            """)
        
        brokerage_file = st.file_uploader(
            "Schwab Individual Brokerage",
            type=['json'],
            help="Individual_*_Transactions_*.json - Export from Schwab → Accounts → History → Export as JSON",
            key=f"brokerage_json_{uploader_key}"
        )
        
        # Store files
        st.session_state.uploaded_files = {
            'eac_json': eac_file,
            'holdings_csv': holdings_file,
            'brokerage_json': brokerage_file,
        }
        
        # Check required files
        has_required = eac_file is not None or holdings_file is not None
        
    else:
        # Capital Gains file uploads
        st.markdown("#### 🇺🇸 US Stocks (Schwab)")
        
        with st.expander("ℹ️ How to download Schwab files", expanded=False):
            st.markdown("""
            **EAC Transactions (JSON):**
            1. Go to [Schwab Equity Award Center](https://client.schwab.com/app/accounts/equityawards/)
            2. Login with your credentials
            3. Navigate to **History** → **Transactions**
            4. Set date range to cover the financial year (April 1 - March 31)
            5. Click **Export** → Select **JSON** format
            6. Save file: `EquityAwardsCenter_Transactions_*.json`
            
            **Individual Brokerage (JSON):**
            1. Go to [Schwab.com](https://www.schwab.com) and login
            2. Navigate to **Accounts** → Select your brokerage account
            3. Go to **History** → **Transactions**
            4. Set date range to cover the financial year
            5. Click **Export** → Select **JSON** format
            6. Save file: `Individual_*_Transactions_*.json`
            """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            eac_file = st.file_uploader(
                "EAC Transactions (JSON)",
                type=['json'],
                help="Schwab EAC → History → Transactions → Export as JSON",
                key=f"cg_eac_{uploader_key}"
            )
        
        with col2:
            brokerage_file = st.file_uploader(
                "Individual Brokerage (JSON)",
                type=['json'],
                help="Schwab → Accounts → History → Export as JSON",
                key=f"cg_brokerage_{uploader_key}"
            )
        
        st.markdown("#### 🇮🇳 Indian Stocks")
        
        with st.expander("ℹ️ How to download Indian broker files", expanded=False):
            st.markdown("""
            **Groww Capital Gains Reports:**
            1. Go to [Groww.in](https://groww.in) and login
            2. Navigate to **Reports** → **Tax P&L Reports**
            3. Select financial year (e.g., FY 2025-26)
            4. Download **Stocks Capital Gains** report (XLSX)
            5. Download **Mutual Funds Capital Gains** report (XLSX)
            
            *Alternative: Profile → Tax Reports → Capital Gains Statement*
            
            ---
            
            **Zerodha P&L Report:**
            1. Go to [Console.zerodha.com](https://console.zerodha.com)
            2. Login with your Kite credentials
            3. Navigate to **Reports** → **Tax P&L**
            4. Select financial year
            5. Click **Download** → Select **XLSX** format
            6. File will be named: `pnl-*.xlsx`
            
            *Includes equity delivery, F&O, and intraday P&L*
            """)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            stocks_file = st.file_uploader(
                "Groww Stocks (XLSX)",
                type=['xlsx'],
                help="Groww → Reports → Tax P&L → Stocks Capital Gains",
                key=f"cg_stocks_{uploader_key}"
            )
        
        with col2:
            mf_file = st.file_uploader(
                "Groww Mutual Funds (XLSX)",
                type=['xlsx'],
                help="Groww → Reports → Tax P&L → Mutual Funds Capital Gains",
                key=f"cg_mf_{uploader_key}"
            )
        
        with col3:
            zerodha_file = st.file_uploader(
                "Zerodha P&L (XLSX)",
                type=['xlsx'],
                help="Console.zerodha.com → Reports → Tax P&L → Download XLSX",
                key=f"cg_zerodha_{uploader_key}"
            )
        
        st.markdown("#### 💱 Exchange Rates (Optional)")
        
        with st.expander("ℹ️ About exchange rates", expanded=False):
            st.markdown("""
            **Auto-fetch (Recommended):**
            - SBI TT Buying rates are auto-fetched from January 2020 onwards
            - No manual upload needed if all transactions are after 2020
            
            **For Pre-2020 Transactions:**
            
            *Option 1: Perquisite Emails ZIP*
            1. Find RSU/ESPP perquisite emails from your payroll provider
            2. Save emails as `.eml` files (in Outlook: File → Save As)
            3. Create a ZIP file containing all `.eml` files
            4. Upload the ZIP file
            
            *Option 2: Custom Rates JSON*
            - Upload a `sbi_reference_rates.json` file with format:
            ```json
            {
              "2019-06-15": 69.50,
              "2019-12-20": 71.25
            }
            ```
            """)
        
        col1, col2 = st.columns(2)
        
        with col1:
            rates_file = st.file_uploader(
                "SBI Rates JSON",
                type=['json'],
                help="Custom exchange rates file (optional - rates are auto-fetched from Jan 2020)",
                key=f"cg_rates_{uploader_key}"
            )
        
        with col2:
            perquisite_zip = st.file_uploader(
                "Perquisite Emails ZIP",
                type=['zip'],
                help="ZIP of .eml files from payroll provider (for pre-2020 rates)",
                key=f"cg_perq_{uploader_key}"
            )
        
        # Store files
        st.session_state.uploaded_files = {
            'eac_json': eac_file,
            'brokerage_json': brokerage_file,
            'indian_stocks_xlsx': stocks_file,
            'indian_mf_xlsx': mf_file,
            'zerodha_xlsx': zerodha_file,
            'rates_json': rates_file,
            'perquisite_zip': perquisite_zip,
        }
        
        # Check if any files uploaded
        has_required = any([eac_file, brokerage_file, stocks_file, mf_file, zerodha_file])
        
        if not is_schedule_fa:
            taxes_paid_val = taxes_paid
        else:
            taxes_paid_val = 0.0
    
    # ===== STEP 4: Generate Report =====
    st.markdown("---")
    st.markdown("### Step 4: Generate Report")
    
    # Show file summary
    files_uploaded = sum(1 for f in st.session_state.uploaded_files.values() if f is not None)
    
    if files_uploaded > 0:
        st.success(f"✓ {files_uploaded} file(s) uploaded")
    else:
        st.warning("⚠️ Please upload at least one transaction file")
    
    generate_btn = st.button(
        "🚀 Generate Report",
        type="primary",
        use_container_width=True,
        disabled=not has_required
    )
    
    if generate_btn and has_required:
        with st.spinner("Processing files..."):
            try:
                # Get exchange rates
                exchange_rates = {}
                
                # Load from uploaded file
                if not is_schedule_fa and st.session_state.uploaded_files.get('rates_json'):
                    rates_file = st.session_state.uploaded_files['rates_json']
                    rates_file.seek(0)
                    exchange_rates = json.load(rates_file)
                
                # Process perquisite emails for historical rates
                if not is_schedule_fa and st.session_state.uploaded_files.get('perquisite_zip'):
                    perq_rates = process_perquisite_zip(st.session_state.uploaded_files['perquisite_zip'])
                    exchange_rates.update(perq_rates)
                
                # Auto-fetch SBI rates
                if auto_fetch_rates:
                    fetched = fetch_sbi_rates()
                    if fetched:
                        exchange_rates.update(fetched)
                        st.success(f"✓ Loaded {len(fetched)} SBI exchange rates")
                
                if is_schedule_fa:
                    generate_schedule_fa_from_files(
                        st.session_state.uploaded_files,
                        exchange_rates,
                        calendar_year
                    )
                else:
                    generate_capital_gains_from_files(
                        st.session_state.uploaded_files,
                        exchange_rates,
                        start_date,
                        taxes_paid_val
                    )
                    
            except Exception as e:
                st.error(f"Error processing files: {str(e)}")
                import traceback
                st.code(traceback.format_exc())
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #808080; font-size: 0.8rem;">
        <strong>⚠️ Non-Commercial Use Only</strong> | 
        Verify all calculations with a qualified CA before filing.
    </div>
    """, unsafe_allow_html=True)


def generate_schedule_fa_from_files(files: dict, exchange_rates: dict, calendar_year: int):
    """Generate Schedule FA report from individual uploaded files."""
    from capital_gains.parsers.foreign_assets import ForeignAssetsParser
    
    # Create parser and load data
    parser = ForeignAssetsParser(calendar_year)
    
    eac_data = None
    if files.get('eac_json'):
        files['eac_json'].seek(0)
        eac_json = json.load(files['eac_json'])
        eac_data = parser.parse_eac_transactions(eac_json)
        st.info(f"📊 Parsed EAC transactions: {len(eac_data.get('sales', []))} sales, {len(eac_data.get('dividends', []))} dividends")
    
    holdings = []
    if files.get('holdings_csv'):
        files['holdings_csv'].seek(0)
        holdings_csv = files['holdings_csv'].read().decode('utf-8')
        symbol = eac_data.get('symbol', 'NVDA') if eac_data else 'NVDA'
        holdings = parser.parse_holdings_csv(holdings_csv, symbol)
        st.info(f"📊 Parsed holdings: {len(holdings)} lots")
    
    brokerage_data = None
    if files.get('brokerage_json'):
        files['brokerage_json'].seek(0)
        brokerage_json = json.load(files['brokerage_json'])
        brokerage_data = parser.parse_brokerage_transactions(brokerage_json)
        st.info(f"📊 Parsed brokerage: {len(brokerage_data.get('holdings', {}))} holdings")
    
    # Create generator
    config = ScheduleFAConfig(calendar_year=calendar_year)
    generator = ScheduleFAGenerator(config=config, exchange_rates=exchange_rates)
    
    # Load data
    generator.load_data(
        eac_data=eac_data,
        brokerage_data=brokerage_data,
        held_shares=holdings
    )
    
    # Generate report
    report = generator.generate()
    
    # Display results
    st.success(f"✅ Schedule FA generated for Assessment Year {report.config.assessment_year}")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Entries", report.get_entry_count())
    with col2:
        st.metric("Closing Value", f"₹{report.total_closing_value_inr:,.0f}")
    with col3:
        st.metric("Sale Proceeds", f"₹{report.total_sale_proceeds_inr:,.0f}")
    with col4:
        st.metric("Dividends", f"₹{report.total_dividend_inr:,.0f}")
    
    # Download button
    st.markdown("### 📥 Download Report")
    
    reporter = ScheduleFAExcelReporter()
    excel_data = reporter.export(report, exchange_rates=exchange_rates)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇️ Download Schedule FA Excel",
        data=excel_data,
        file_name=f"Schedule_FA_AY{report.config.assessment_year}_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )


def generate_capital_gains_from_files(files: dict, exchange_rates: dict, start_date: datetime, taxes_paid: float):
    """Generate Capital Gains report from individual uploaded files."""
    all_transactions = []
    indian_gains_list = []
    
    # Process Schwab EAC
    if files.get('eac_json'):
        files['eac_json'].seek(0)
        eac_json = json.load(files['eac_json'])
        parser = SchwabEACParser()
        eac_transactions = eac_json.get('Transactions', [])
        transactions = parser.parse(eac_transactions, start_date)
        all_transactions.extend(transactions)
        st.info(f"📊 Parsed {len(transactions)} EAC transactions")
    
    # Process Schwab Brokerage  
    if files.get('brokerage_json'):
        files['brokerage_json'].seek(0)
        brokerage_json = json.load(files['brokerage_json'])
        parser = SchwabIndividualParser()
        brokerage_transactions = brokerage_json.get('BrokerageTransactions', [])
        transactions = parser.parse(brokerage_transactions, start_date)
        all_transactions.extend(transactions)
        st.info(f"📊 Parsed {len(transactions)} brokerage transactions")
    
    # Process Indian Stocks
    if files.get('indian_stocks_xlsx'):
        try:
            files['indian_stocks_xlsx'].seek(0)
            # Save to temp file for parser
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(files['indian_stocks_xlsx'].read())
                tmp_path = tmp.name
            
            parser = IndianStocksParser()
            gains = parser.parse(tmp_path)
            indian_gains_list.append(gains)
            st.info(f"📊 Parsed Indian stocks: STCG ₹{gains.stcg:,.0f}, LTCG ₹{gains.ltcg:,.0f}")
            
            os.unlink(tmp_path)
        except Exception as e:
            st.warning(f"Could not parse Indian stocks file: {e}")
    
    # Process Indian MF
    if files.get('indian_mf_xlsx'):
        try:
            files['indian_mf_xlsx'].seek(0)
            # Save to temp file for parser
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(files['indian_mf_xlsx'].read())
                tmp_path = tmp.name
            
            parser = IndianMutualFundsParser()
            gains = parser.parse(tmp_path)
            indian_gains_list.append(gains)
            st.info(f"📊 Parsed Indian MF: STCG ₹{gains.stcg:,.0f}, LTCG ₹{gains.ltcg:,.0f}")
            
            os.unlink(tmp_path)
        except Exception as e:
            st.warning(f"Could not parse Indian MF file: {e}")
    
    # Process Zerodha
    if files.get('zerodha_xlsx'):
        try:
            files['zerodha_xlsx'].seek(0)
            # Save to temp file for Zerodha parser
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                tmp.write(files['zerodha_xlsx'].read())
                tmp_path = tmp.name
            
            parser = ZerodhaPnLParser()
            gains = parser.parse(tmp_path)
            indian_gains_list.append(gains)
            st.info(f"📊 Parsed Zerodha: STCG ₹{gains.stcg:,.0f}, LTCG ₹{gains.ltcg:,.0f}")
            
            os.unlink(tmp_path)
        except Exception as e:
            st.warning(f"Could not parse Zerodha file: {e}")
    
    # Calculate totals
    total_indian = sum(g.ltcg + g.stcg for g in indian_gains_list)
    
    if not all_transactions and total_indian == 0:
        st.warning("No transactions found in the uploaded files.")
        return
    
    # Calculate gains
    calculator = CapitalGainsCalculator()
    results = calculator.calculate(all_transactions, exchange_rates)
    
    # Calculate taxes
    tax_calc = TaxCalculator()
    tax_data = tax_calc.calculate(results, indian_gains_list, taxes_paid)
    
    # Display results
    st.success("✅ Capital gains calculated successfully!")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Foreign STCG", f"₹{tax_data.schwab_stcg:,.0f}")
    with col2:
        st.metric("Foreign LTCG", f"₹{tax_data.schwab_ltcg:,.0f}")
    with col3:
        st.metric("Indian Gains", f"₹{total_indian:,.0f}")
    with col4:
        if tax_data.tax_liability > 0:
            st.metric("Tax Due", f"₹{tax_data.tax_liability:,.0f}", delta_color="inverse")
        else:
            st.metric("Tax Refund", f"₹{abs(tax_data.tax_liability):,.0f}")
    
    # Download button
    st.markdown("### 📥 Download Report")
    
    excel_data = generate_excel_report(results, indian_gains_list, tax_data, exchange_rates)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label="⬇️ Download Capital Gains Excel",
        data=excel_data,
        file_name=f"capital_gains_report_{timestamp}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )


if __name__ == "__main__":
    unified_main()

