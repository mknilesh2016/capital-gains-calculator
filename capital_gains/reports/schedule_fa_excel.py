"""
Schedule FA Excel Report Generator.
Generates Excel reports for Schedule FA (Foreign Assets).
"""

import io
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import xlsxwriter
    XLSXWRITER_AVAILABLE = True
except ImportError:
    XLSXWRITER_AVAILABLE = False

from ..schedule_fa.models import ScheduleFAReport, ForeignAssetEntry


def format_indian_currency(amount: float) -> str:
    """
    Format number in Indian numbering system (lakhs, crores).
    
    Indian format: 1,00,000 (1 lakh), 1,00,00,000 (1 crore)
    """
    if amount < 0:
        return '-' + format_indian_currency(-amount)
    
    amount = round(amount)
    s = str(int(amount))
    
    if len(s) <= 3:
        return '₹' + s
    
    # Last 3 digits
    result = s[-3:]
    s = s[:-3]
    
    # Then groups of 2
    while s:
        result = s[-2:] + ',' + result
        s = s[:-2]
    
    return '₹' + result


class ScheduleFAExcelReporter:
    """
    Generates Excel reports for Schedule FA.
    
    Creates a multi-sheet workbook with:
    - Summary sheet
    - Schedule FA (combined ITR format)
    - Regular Sales details
    - Tax Sales details  
    - Held Shares details
    - Brokerage transactions
    - Dividends (FSI)
    - Exchange Rates reference
    """
    
    def __init__(self):
        self.formats = {}
    
    def _define_formats(self, workbook):
        """Define Excel cell formats."""
        self.formats = {
            'header': workbook.add_format({
                'bold': True, 'bg_color': '#4472C4', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            }),
            'subheader': workbook.add_format({
                'bold': True, 'bg_color': '#B4C6E7', 'border': 1, 'align': 'center'
            }),
            'section_header': workbook.add_format({
                'bold': True, 'font_size': 11, 'bg_color': '#2E75B6', 'font_color': 'white',
                'align': 'left', 'border': 1
            }),
            'currency_usd': workbook.add_format({'num_format': '$#,##0.00', 'border': 1}),
            'currency_inr': workbook.add_format({'num_format': '₹#,##0', 'border': 1}),
            'number': workbook.add_format({'num_format': '#,##0.00', 'border': 1}),
            'int': workbook.add_format({'num_format': '#,##0', 'border': 1}),
            'date': workbook.add_format({'num_format': 'dd/mm/yyyy', 'border': 1, 'align': 'center'}),
            'text': workbook.add_format({'border': 1, 'align': 'left'}),
            'center': workbook.add_format({'border': 1, 'align': 'center'}),
            'total': workbook.add_format({
                'bold': True, 'bg_color': '#E2EFDA', 'border': 2,
                'num_format': '₹#,##0', 'align': 'right'
            }),
            'title': workbook.add_format({
                'bold': True, 'font_size': 14, 'bg_color': '#1F4E79', 'font_color': 'white',
                'align': 'center', 'valign': 'vcenter', 'border': 2
            }),
        }
    
    def export(
        self,
        report: ScheduleFAReport,
        filepath: str = None,
        exchange_rates: Dict[str, float] = None
    ) -> Optional[bytes]:
        """
        Export Schedule FA report to Excel.
        
        Args:
            report: ScheduleFAReport object
            filepath: Output file path (optional - returns bytes if None)
            exchange_rates: Exchange rates dictionary for reference sheet
        
        Returns:
            Excel file as bytes if filepath is None, otherwise None
        """
        if not XLSXWRITER_AVAILABLE:
            raise ImportError("xlsxwriter is required for Excel export")
        
        # Create workbook
        if filepath:
            workbook = xlsxwriter.Workbook(filepath, {'remove_timezone': True})
            output_buffer = None
        else:
            output_buffer = io.BytesIO()
            workbook = xlsxwriter.Workbook(output_buffer, {'remove_timezone': True})
        
        self._define_formats(workbook)
        
        # Generate sheets
        self._generate_summary_sheet(workbook, report)
        self._generate_schedule_fa_sheet(workbook, report)
        self._generate_details_sheet(workbook, report, 'Regular Sales', 'RSU|ESPP')
        self._generate_details_sheet(workbook, report, 'Tax Sales', 'RSU-TAX|ESPP-TAX')
        self._generate_details_sheet(workbook, report, 'Held Shares', 'RSU|ESPP', held_only=True)
        self._generate_brokerage_sheet(workbook, report)
        self._generate_dividends_sheet(workbook, report)
        if exchange_rates:
            self._generate_rates_sheet(workbook, exchange_rates, report.config)
        
        workbook.close()
        
        if output_buffer:
            output_buffer.seek(0)
            return output_buffer.read()
        
        return None
    
    def _generate_summary_sheet(self, workbook, report: ScheduleFAReport):
        """Generate summary sheet."""
        ws = workbook.add_worksheet('Summary')
        ws.set_column('A:A', 35)
        ws.set_column('B:B', 20)
        
        row = 0
        ws.merge_range(row, 0, row, 1, 
            f'SCHEDULE FA REPORT - AY {report.config.assessment_year}', 
            self.formats['title'])
        row += 2
        
        # Summary items - using Indian number format (lakhs, crores)
        items = [
            ('Calendar Year', report.config.calendar_year),
            ('Assessment Year', report.config.assessment_year),
            ('', ''),
            ('SECTION A3 - FOREIGN EQUITY', ''),
            ('Total Entries', report.get_entry_count()),
            ('Regular Sales (INR)', format_indian_currency(report.regular_sales_total_inr)),
            ('Tax Withholding Sales (INR)', format_indian_currency(report.tax_sales_total_inr)),
            ('Held Shares Closing (INR)', format_indian_currency(report.held_shares_closing_inr)),
            ('Brokerage Closing (INR)', format_indian_currency(report.brokerage_closing_inr)),
            ('', ''),
            ('TOTALS', ''),
            ('Total Initial Value (INR)', format_indian_currency(report.total_initial_value_inr)),
            ('Total Peak Value (INR)', format_indian_currency(report.total_peak_value_inr)),
            ('Total Closing Value (INR)', format_indian_currency(report.total_closing_value_inr)),
            ('Total Sale Proceeds (INR)', format_indian_currency(report.total_sale_proceeds_inr)),
            ('', ''),
            ('SCHEDULE FSI - DIVIDENDS', ''),
            ('Total Dividend Income (INR)', format_indian_currency(report.total_dividend_inr)),
            ('Tax Withheld (INR)', format_indian_currency(report.total_dividend_tax_inr)),
        ]
        
        for label, value in items:
            if label:
                ws.write(row, 0, label, self.formats['text'])
                ws.write(row, 1, value, self.formats['center'])
            row += 1
        
        # Add reference data section showing key prices and rates used
        row += 1
        ws.merge_range(row, 0, row, 1, 'KEY REFERENCE DATA', self.formats['section_header'])
        row += 1
        
        # Extract unique closing prices and rates from entries
        seen_symbols = set()
        closing_rate = 0
        for entry in report.equity_entries:
            if entry.closing_price_usd > 0 and entry.entity_name not in seen_symbols:
                seen_symbols.add(entry.entity_name)
                ws.write(row, 0, f'{entry.entity_name[:20]} Stock Close (USD)', self.formats['text'])
                ws.write(row, 1, f'${entry.closing_price_usd:.2f}', self.formats['center'])
                row += 1
                if entry.rate_at_close > 0:
                    closing_rate = entry.rate_at_close
        
        # Show USD-INR closing rate once
        if closing_rate > 0:
            ws.write(row, 0, 'USD-INR Rate (Dec 31)', self.formats['text'])
            ws.write(row, 1, f'{closing_rate:.2f}', self.formats['center'])
            row += 1
    
    def _generate_schedule_fa_sheet(self, workbook, report: ScheduleFAReport):
        """Generate combined Schedule FA sheet in ITR format."""
        ws = workbook.add_worksheet('Schedule FA')
        
        # Set column widths
        ws.set_column('A:A', 5)
        ws.set_column('B:B', 28)
        ws.set_column('C:C', 20)
        ws.set_column('D:D', 15)
        ws.set_column('E:E', 8)
        ws.set_column('F:F', 10)
        ws.set_column('G:G', 12)
        ws.set_column('H:M', 15)
        
        row = 0
        
        # Title
        ws.merge_range(row, 0, row, 12, 
            'SCHEDULE FA - DETAILS OF FOREIGN ASSETS AND INCOME FROM ANY SOURCE OUTSIDE INDIA', 
            self.formats['title'])
        row += 1
        
        ws.merge_range(row, 0, row, 12, 
            f'Assessment Year: {report.config.assessment_year} | Calendar Year: {report.config.calendar_year}', 
            self.formats['subheader'])
        row += 2
        
        # Section A3 Header
        ws.merge_range(row, 0, row, 12, 
            'A3. Details of Foreign Equity and Debt Interest held at any time during the calendar year', 
            self.formats['section_header'])
        row += 1
        
        # Column headers
        headers = ['Sl', 'Country', 'Entity Name', 'Address', 'ZIP', 'Nature', 'Date Acquired',
                   'Initial (INR)', 'Peak (INR)', 'Closing (INR)', 'Dividend (INR)', 
                   'Sale Date', 'Proceeds (INR)']
        for col, h in enumerate(headers):
            ws.write(row, col, h, self.formats['header'])
        row += 1
        
        # Write entries
        totals = {
            'initial': 0, 'peak': 0, 'closing': 0, 'dividend': 0, 'proceeds': 0
        }
        
        for entry in report.equity_entries:
            ws.write(row, 0, entry.serial_no, self.formats['int'])
            ws.write(row, 1, f'{entry.country_code}-{entry.country_name}', self.formats['text'])
            ws.write(row, 2, entry.entity_name, self.formats['text'])
            ws.write(row, 3, entry.entity_address, self.formats['text'])
            ws.write(row, 4, entry.zip_code, self.formats['center'])
            ws.write(row, 5, entry.nature_of_entity, self.formats['center'])
            
            if entry.acquisition_date:
                ws.write(row, 6, entry.acquisition_date, self.formats['date'])
            else:
                ws.write(row, 6, '', self.formats['text'])
            
            ws.write(row, 7, entry.initial_value_inr, self.formats['currency_inr'])
            ws.write(row, 8, entry.peak_value_inr, self.formats['currency_inr'])
            ws.write(row, 9, entry.closing_value_inr, self.formats['currency_inr'])
            ws.write(row, 10, entry.dividend_income_inr, self.formats['currency_inr'])
            
            if entry.sale_date:
                ws.write(row, 11, entry.sale_date, self.formats['date'])
            else:
                ws.write(row, 11, '', self.formats['text'])
            
            ws.write(row, 12, entry.sale_proceeds_inr, self.formats['currency_inr'])
            
            totals['initial'] += entry.initial_value_inr
            totals['peak'] += entry.peak_value_inr
            totals['closing'] += entry.closing_value_inr
            totals['dividend'] += entry.dividend_income_inr
            totals['proceeds'] += entry.sale_proceeds_inr
            row += 1
        
        # Totals row
        row += 1
        ws.merge_range(row, 0, row, 6, 'GRAND TOTAL (A3)', self.formats['total'])
        ws.write(row, 7, totals['initial'], self.formats['total'])
        ws.write(row, 8, totals['peak'], self.formats['total'])
        ws.write(row, 9, totals['closing'], self.formats['total'])
        ws.write(row, 10, totals['dividend'], self.formats['total'])
        ws.write(row, 11, '', self.formats['total'])
        ws.write(row, 12, totals['proceeds'], self.formats['total'])
        
        row += 3
        
        # Section A1 - Custodial Accounts
        ws.merge_range(row, 0, row, 12, 
            'A1. Details of Foreign Depository Accounts held at any time during the calendar year', 
            self.formats['section_header'])
        row += 1
        
        a1_headers = ['Sl', 'Country', 'Institution', 'Address', 'ZIP', 'Account#',
                      'Status', 'Peak Balance', 'Closing Balance', '', '', '', '']
        for col, h in enumerate(a1_headers):
            ws.write(row, col, h, self.formats['header'])
        row += 1
        
        for account in report.custodial_accounts:
            ws.write(row, 0, account.serial_no, self.formats['int'])
            ws.write(row, 1, f'{account.country_code}-{account.country_name}', self.formats['text'])
            ws.write(row, 2, account.institution_name, self.formats['text'])
            ws.write(row, 3, account.institution_address, self.formats['text'])
            ws.write(row, 4, account.zip_code, self.formats['center'])
            ws.write(row, 5, account.account_number, self.formats['center'])
            ws.write(row, 6, account.status, self.formats['center'])
            ws.write(row, 7, account.peak_balance_inr, self.formats['currency_inr'])
            ws.write(row, 8, account.closing_balance_inr, self.formats['currency_inr'])
            row += 1
    
    def _generate_details_sheet(
        self, 
        workbook, 
        report: ScheduleFAReport, 
        sheet_name: str, 
        nature_filter: str,
        held_only: bool = False
    ):
        """Generate detail sheet for specific entry types with calculation breakdown."""
        ws = workbook.add_worksheet(sheet_name)
        
        ws.set_column('A:A', 5)
        ws.set_column('B:C', 10)
        ws.set_column('D:H', 11)
        ws.set_column('I:L', 10)
        ws.set_column('M:P', 15)
        
        # Filter entries
        filter_types = nature_filter.split('|')
        if held_only:
            entries = [e for e in report.equity_entries 
                      if e.nature_of_entity in filter_types and e.sale_date is None]
        else:
            entries = [e for e in report.equity_entries 
                      if e.nature_of_entity in filter_types and e.sale_date is not None]
        
        row = 0
        ws.merge_range(row, 0, row, 15, 
            f'{sheet_name.upper()} - CY {report.config.calendar_year}', 
            self.formats['title'])
        row += 1
        
        # Different headers for held vs sold
        if held_only:
            headers = ['Sl', 'Type', 'Acq Date', 'Shares', 'Cost USD', 'Peak USD', 
                       'Close USD', 'USD-INR Acq', 'USD-INR Peak', 'USD-INR Close',
                       'Initial INR', 'Peak INR', 'Close INR']
        else:
            headers = ['Sl', 'Type', 'Acq Date', 'Shares', 'Cost USD', 'Peak USD', 
                       'Sale USD', 'USD-INR Acq', 'USD-INR Peak', 'USD-INR Sale',
                       'Initial INR', 'Peak INR', 'Close INR', 'Proceeds INR']
        
        for col, h in enumerate(headers):
            ws.write(row, col, h, self.formats['header'])
        row += 1
        
        total_initial = total_peak = total_close = total_proceeds = 0
        
        for i, entry in enumerate(entries, 1):
            ws.write(row, 0, i, self.formats['int'])
            ws.write(row, 1, entry.nature_of_entity, self.formats['center'])
            if entry.acquisition_date:
                ws.write(row, 2, entry.acquisition_date, self.formats['date'])
            ws.write(row, 3, entry.shares, self.formats['number'])
            ws.write(row, 4, entry.cost_per_share_usd, self.formats['currency_usd'])
            ws.write(row, 5, entry.peak_price_usd, self.formats['currency_usd'])
            
            if held_only:
                ws.write(row, 6, entry.closing_price_usd, self.formats['currency_usd'])
                ws.write(row, 7, entry.rate_at_acquisition, self.formats['number'])
                ws.write(row, 8, entry.rate_at_peak, self.formats['number'])
                ws.write(row, 9, entry.rate_at_close, self.formats['number'])
                ws.write(row, 10, entry.initial_value_inr, self.formats['currency_inr'])
                ws.write(row, 11, entry.peak_value_inr, self.formats['currency_inr'])
                ws.write(row, 12, entry.closing_value_inr, self.formats['currency_inr'])
            else:
                ws.write(row, 6, entry.sale_price_usd, self.formats['currency_usd'])
                ws.write(row, 7, entry.rate_at_acquisition, self.formats['number'])
                ws.write(row, 8, entry.rate_at_peak, self.formats['number'])
                ws.write(row, 9, entry.rate_at_sale, self.formats['number'])
                ws.write(row, 10, entry.initial_value_inr, self.formats['currency_inr'])
                ws.write(row, 11, entry.peak_value_inr, self.formats['currency_inr'])
                ws.write(row, 12, entry.closing_value_inr, self.formats['currency_inr'])
                ws.write(row, 13, entry.sale_proceeds_inr, self.formats['currency_inr'])
            
            total_initial += entry.initial_value_inr
            total_peak += entry.peak_value_inr
            total_close += entry.closing_value_inr
            total_proceeds += entry.sale_proceeds_inr
            row += 1
        
        row += 1
        ws.merge_range(row, 0, row, 9, 'TOTAL', self.formats['total'])
        ws.write(row, 10, total_initial, self.formats['total'])
        ws.write(row, 11, total_peak, self.formats['total'])
        ws.write(row, 12, total_close, self.formats['total'])
        if not held_only:
            ws.write(row, 13, total_proceeds, self.formats['total'])
    
    def _generate_brokerage_sheet(self, workbook, report: ScheduleFAReport):
        """Generate brokerage holdings sheet (aggregated by symbol)."""
        ws = workbook.add_worksheet('Brokerage')
        
        ws.set_column('A:A', 5)
        ws.set_column('B:C', 8)
        ws.set_column('D:D', 25)
        ws.set_column('E:F', 12)
        ws.set_column('G:K', 15)
        
        # Filter brokerage entries (by source)
        entries = [e for e in report.equity_entries if e.source == 'Brokerage']
        
        row = 0
        ws.merge_range(row, 0, row, 10, 
            f'BROKERAGE HOLDINGS - CY {report.config.calendar_year}', 
            self.formats['title'])
        row += 1
        
        headers = ['Sl', 'Type', 'Entity', 'Acq Date', 'Shares', 
                   'Initial INR', 'Peak INR', 'Close INR', 'Proceeds INR', 'Sale Date']
        for col, h in enumerate(headers):
            ws.write(row, col, h, self.formats['header'])
        row += 1
        
        total_initial = total_peak = total_close = total_proceeds = 0
        
        for i, entry in enumerate(entries, 1):
            ws.write(row, 0, i, self.formats['int'])
            ws.write(row, 1, entry.nature_of_entity, self.formats['center'])
            ws.write(row, 2, entry.entity_name[:24], self.formats['text'])
            if entry.acquisition_date:
                ws.write(row, 3, entry.acquisition_date, self.formats['date'])
            ws.write(row, 4, entry.shares, self.formats['number'])
            ws.write(row, 5, entry.initial_value_inr, self.formats['currency_inr'])
            ws.write(row, 6, entry.peak_value_inr, self.formats['currency_inr'])
            ws.write(row, 7, entry.closing_value_inr, self.formats['currency_inr'])
            ws.write(row, 8, entry.sale_proceeds_inr, self.formats['currency_inr'])
            if entry.sale_date:
                ws.write(row, 9, entry.sale_date, self.formats['date'])
            
            total_initial += entry.initial_value_inr
            total_peak += entry.peak_value_inr
            total_close += entry.closing_value_inr
            total_proceeds += entry.sale_proceeds_inr
            row += 1
        
        row += 1
        ws.merge_range(row, 0, row, 4, 'TOTAL', self.formats['total'])
        ws.write(row, 5, total_initial, self.formats['total'])
        ws.write(row, 6, total_peak, self.formats['total'])
        ws.write(row, 7, total_close, self.formats['total'])
        ws.write(row, 8, total_proceeds, self.formats['total'])
    
    def _generate_dividends_sheet(self, workbook, report: ScheduleFAReport):
        """Generate dividends sheet for Schedule FSI."""
        ws = workbook.add_worksheet('Dividends (FSI)')
        
        ws.set_column('A:A', 5)
        ws.set_column('B:D', 12)
        ws.set_column('E:I', 15)
        
        row = 0
        ws.merge_range(row, 0, row, 8, 
            f'SCHEDULE FSI - DIVIDEND INCOME (CY {report.config.calendar_year})', 
            self.formats['title'])
        row += 1
        
        headers = ['Sl', 'Symbol', 'Date', 'Source', 'Gross USD', 'Tax USD', 
                   'Rate', 'Gross INR', 'Tax INR']
        for col, h in enumerate(headers):
            ws.write(row, col, h, self.formats['header'])
        row += 1
        
        total_gross = total_tax = 0
        
        for i, div in enumerate(report.dividends, 1):
            ws.write(row, 0, i, self.formats['int'])
            ws.write(row, 1, div.symbol, self.formats['center'])
            if div.date:
                ws.write(row, 2, div.date, self.formats['date'])
            ws.write(row, 3, div.source, self.formats['text'])
            ws.write(row, 4, div.gross_amount_usd, self.formats['currency_usd'])
            ws.write(row, 5, div.tax_withheld_usd, self.formats['currency_usd'])
            ws.write(row, 6, div.exchange_rate, self.formats['number'])
            ws.write(row, 7, div.gross_amount_inr, self.formats['currency_inr'])
            ws.write(row, 8, div.tax_withheld_inr, self.formats['currency_inr'])
            
            total_gross += div.gross_amount_inr
            total_tax += div.tax_withheld_inr
            row += 1
        
        row += 1
        ws.merge_range(row, 0, row, 6, 'TOTAL', self.formats['total'])
        ws.write(row, 7, total_gross, self.formats['total'])
        ws.write(row, 8, total_tax, self.formats['total'])
    
    def _generate_rates_sheet(self, workbook, rates: Dict[str, float], config):
        """Generate exchange rates reference sheet."""
        ws = workbook.add_worksheet('Exchange Rates')
        
        ws.set_column('A:A', 15)
        ws.set_column('B:B', 12)
        
        row = 0
        ws.merge_range(row, 0, row, 1, 
            f'SBI TT BUYING RATES (CY {config.calendar_year})', 
            self.formats['title'])
        row += 1
        
        ws.write(row, 0, 'Date', self.formats['header'])
        ws.write(row, 1, 'Rate (INR)', self.formats['header'])
        row += 1
        
        # Filter and sort rates for the calendar year
        cy_rates = {k: v for k, v in rates.items() 
                   if k.startswith(str(config.calendar_year))}
        
        for date_str in sorted(cy_rates.keys()):
            ws.write(row, 0, date_str, self.formats['text'])
            ws.write(row, 1, cy_rates[date_str], self.formats['number'])
            row += 1

