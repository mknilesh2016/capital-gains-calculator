"""
Tax calculation module for capital gains.

This module provides tax rates, rules, and calculation logic
based on Indian Income Tax Act provisions.
"""

from dataclasses import dataclass
from typing import List

from .models import SaleTransaction, IndianGains, TaxData


@dataclass
class TaxRates:
    """
    Tax rates for capital gains (FY 2024-25 / AY 2025-26).
    
    Base Rates (as per Finance Act 2024):
    - Indian STCG (Section 111A): 20%
    - Indian LTCG (Section 112A): 12.5%
    - Foreign LTCG (Section 112): 12.5% (without indexation)
    - Foreign STCG: Slab rate (30% for income > 15 lakh)
    
    Surcharge:
    - Capital gains at special rates: Max 15%
    - Income at slab rates (>2 Cr): 25%
    
    Education Cess: 4%
    
    Effective Rates (Base × Surcharge × Cess):
    - Indian STCG: 20% × 1.15 × 1.04 = 23.92%
    - Indian LTCG: 12.5% × 1.15 × 1.04 = 14.95%
    - Foreign LTCG: 12.5% × 1.15 × 1.04 = 14.95%
    - Foreign STCG: 30% × 1.25 × 1.04 = 39%
    """
    
    # Effective rates (including surcharge and cess)
    INDIAN_LTCG: float = 0.1495     # 12.5% + 15% SC + 4% Cess
    FOREIGN_LTCG: float = 0.1495   # 12.5% + 15% SC + 4% Cess
    INDIAN_STCG: float = 0.2392    # 20% + 15% SC + 4% Cess
    FOREIGN_STCG: float = 0.39     # 30% + 25% SC + 4% Cess
    
    # Exemption limit for Section 112A (Indian LTCG with STT)
    LTCG_EXEMPTION: float = 125000.0  # ₹1,25,000


class TaxCalculator:
    """
    Calculator for computing tax liability on capital gains.
    
    Applies Indian tax rules for:
    - Long-term and short-term classification
    - LTCG exemption under Section 112A
    - Loss set-off provisions
    - Different rates for Indian vs Foreign assets
    
    Example:
        >>> calculator = TaxCalculator()
        >>> tax_data = calculator.calculate(
        ...     transactions=schwab_transactions,
        ...     indian_gains=[stocks_gains, mf_gains],
        ...     taxes_paid=100000.0
        ... )
        >>> print(f"Tax liability: ₹{tax_data.tax_liability:,.2f}")
    """
    
    def __init__(self, rates: TaxRates = None):
        """
        Initialize the tax calculator.
        
        Args:
            rates: Tax rates to use. Defaults to current FY rates.
        """
        self.rates = rates or TaxRates()
    
    def calculate(
        self,
        transactions: List[SaleTransaction] = None,
        indian_gains: List[IndianGains] = None,
        taxes_paid: float = 0.0
    ) -> TaxData:
        """
        Calculate complete tax liability.
        
        Args:
            transactions: List of Schwab/foreign stock transactions
            indian_gains: List of Indian gains (stocks, MFs)
            taxes_paid: Taxes already paid during the year
            
        Returns:
            TaxData object with complete tax calculation
        """
        transactions = transactions or []
        indian_gains = indian_gains or []
        
        # Initialize tax data
        tax_data = TaxData()
        tax_data.taxes_paid = taxes_paid
        tax_data.ltcg_rebate = self.rates.LTCG_EXEMPTION
        
        # Store rates
        tax_data.indian_ltcg_rate = self.rates.INDIAN_LTCG
        tax_data.foreign_ltcg_rate = self.rates.FOREIGN_LTCG
        tax_data.indian_stcg_rate = self.rates.INDIAN_STCG
        tax_data.foreign_stcg_rate = self.rates.FOREIGN_STCG
        
        # Calculate Schwab gains
        tax_data.schwab_ltcg = sum(
            t.capital_gain_inr for t in transactions if t.is_long_term
        )
        tax_data.schwab_stcg = sum(
            t.capital_gain_inr for t in transactions if not t.is_long_term
        )
        
        # Calculate Indian gains
        tax_data.indian_ltcg = sum(g.ltcg for g in indian_gains)
        tax_data.indian_stcg = sum(g.stcg for g in indian_gains)
        
        # Calculate totals
        tax_data.total_ltcg = tax_data.schwab_ltcg + tax_data.indian_ltcg
        tax_data.total_stcg = tax_data.schwab_stcg + tax_data.indian_stcg
        
        # Step 1: Apply LTCG exemption (Section 112A - only for Indian)
        self._apply_ltcg_exemption(tax_data)
        
        # Step 2: Loss set-off
        self._apply_loss_setoff(tax_data)
        
        # Step 3: Calculate taxes
        self._calculate_taxes(tax_data)
        
        # Step 4: Calculate liability
        tax_data.tax_liability = tax_data.total_tax - tax_data.taxes_paid
        
        return tax_data
    
    def _apply_ltcg_exemption(self, tax_data: TaxData) -> None:
        """
        Apply LTCG exemption under Section 112A.
        
        The ₹1,25,000 exemption applies only to Indian LTCG
        (equity with STT paid).
        """
        if tax_data.indian_ltcg > 0:
            tax_data.rebate_used = min(tax_data.indian_ltcg, self.rates.LTCG_EXEMPTION)
            tax_data.indian_ltcg_after_rebate = max(
                0, tax_data.indian_ltcg - self.rates.LTCG_EXEMPTION
            )
        else:
            tax_data.rebate_used = 0
            tax_data.indian_ltcg_after_rebate = tax_data.indian_ltcg
    
    def _apply_loss_setoff(self, tax_data: TaxData) -> None:
        """
        Apply loss set-off provisions per Indian Income Tax rules.
        
        Rules:
        - STCG losses can be set off against both STCG and LTCG gains
        - LTCG losses can ONLY be set off against LTCG gains
        - Set-off priority: Same head first, then cross-head
        
        Order of set-off:
        1. STCG losses set off against STCG gains (same head)
        2. Remaining STCG losses set off against LTCG gains
        3. LTCG losses set off against LTCG gains only
        """
        # Step 1: Identify losses and gains separately
        foreign_ltcg_loss = abs(min(0, tax_data.schwab_ltcg))
        indian_ltcg_loss = abs(min(0, tax_data.indian_ltcg_after_rebate))
        foreign_stcg_loss = abs(min(0, tax_data.schwab_stcg))
        indian_stcg_loss = abs(min(0, tax_data.indian_stcg))
        
        foreign_ltcg_gain = max(0, tax_data.schwab_ltcg)
        indian_ltcg_gain = max(0, tax_data.indian_ltcg_after_rebate)
        foreign_stcg_gain = max(0, tax_data.schwab_stcg)
        indian_stcg_gain = max(0, tax_data.indian_stcg)
        
        total_ltcg_loss = foreign_ltcg_loss + indian_ltcg_loss
        total_stcg_loss = foreign_stcg_loss + indian_stcg_loss
        total_ltcg_gain = foreign_ltcg_gain + indian_ltcg_gain
        total_stcg_gain = foreign_stcg_gain + indian_stcg_gain
        
        # Store gains/losses for transparency
        tax_data.foreign_ltcg_gain = foreign_ltcg_gain
        tax_data.foreign_ltcg_loss = foreign_ltcg_loss
        tax_data.indian_ltcg_gain = indian_ltcg_gain
        tax_data.indian_ltcg_loss = indian_ltcg_loss
        tax_data.foreign_stcg_gain = foreign_stcg_gain
        tax_data.foreign_stcg_loss = foreign_stcg_loss
        tax_data.indian_stcg_gain = indian_stcg_gain
        tax_data.indian_stcg_loss = indian_stcg_loss
        
        # Step 2: STCG losses set off against STCG gains first
        stcg_loss_remaining = total_stcg_loss
        
        # Set off against Foreign STCG first (higher tax rate)
        setoff_against_foreign_stcg = min(stcg_loss_remaining, foreign_stcg_gain)
        foreign_stcg_after_setoff = foreign_stcg_gain - setoff_against_foreign_stcg
        stcg_loss_remaining -= setoff_against_foreign_stcg
        
        # Then against Indian STCG
        setoff_against_indian_stcg = min(stcg_loss_remaining, indian_stcg_gain)
        indian_stcg_after_setoff = indian_stcg_gain - setoff_against_indian_stcg
        stcg_loss_remaining -= setoff_against_indian_stcg
        
        # Step 3: Remaining STCG losses set off against LTCG gains
        setoff_stcg_against_ltcg = min(stcg_loss_remaining, total_ltcg_gain)
        ltcg_after_stcg_setoff = total_ltcg_gain - setoff_stcg_against_ltcg
        
        # Step 4: LTCG losses set off against remaining LTCG gains
        setoff_ltcg_against_ltcg = min(total_ltcg_loss, ltcg_after_stcg_setoff)
        final_ltcg = ltcg_after_stcg_setoff - setoff_ltcg_against_ltcg
        
        # Store set-off amounts for transparency
        tax_data.stcg_loss_vs_foreign_stcg = setoff_against_foreign_stcg
        tax_data.stcg_loss_vs_indian_stcg = setoff_against_indian_stcg
        tax_data.stcg_loss_vs_ltcg = setoff_stcg_against_ltcg
        tax_data.ltcg_loss_vs_ltcg = setoff_ltcg_against_ltcg
        
        # Step 5: Distribute remaining LTCG proportionally between foreign and Indian
        if total_ltcg_gain > 0:
            foreign_ltcg_ratio = foreign_ltcg_gain / total_ltcg_gain
            indian_ltcg_ratio = indian_ltcg_gain / total_ltcg_gain
        else:
            foreign_ltcg_ratio = 0
            indian_ltcg_ratio = 0
        
        tax_data.foreign_ltcg_taxable = final_ltcg * foreign_ltcg_ratio
        tax_data.indian_ltcg_taxable = final_ltcg * indian_ltcg_ratio
        tax_data.foreign_stcg_taxable = foreign_stcg_after_setoff
        tax_data.indian_stcg_taxable = indian_stcg_after_setoff
        
        # Net totals for reporting
        tax_data.net_ltcg = final_ltcg
        tax_data.net_stcg = foreign_stcg_after_setoff + indian_stcg_after_setoff
    
    def _calculate_taxes(self, tax_data: TaxData) -> None:
        """Calculate taxes for each category."""
        # Foreign LTCG @ 14.95%
        tax_data.foreign_ltcg_tax = tax_data.foreign_ltcg_taxable * self.rates.FOREIGN_LTCG
        
        # Indian LTCG @ 14.95%
        tax_data.indian_ltcg_tax = tax_data.indian_ltcg_taxable * self.rates.INDIAN_LTCG
        
        # Total LTCG tax
        tax_data.ltcg_tax = tax_data.foreign_ltcg_tax + tax_data.indian_ltcg_tax
        
        # Indian STCG @ 23.92%
        tax_data.indian_stcg_tax = tax_data.indian_stcg_taxable * self.rates.INDIAN_STCG
        
        # Foreign STCG @ 39%
        tax_data.foreign_stcg_tax = tax_data.foreign_stcg_taxable * self.rates.FOREIGN_STCG
        
        # Total STCG tax
        tax_data.stcg_tax = tax_data.indian_stcg_tax + tax_data.foreign_stcg_tax
        
        # Total tax
        tax_data.total_tax = tax_data.ltcg_tax + tax_data.stcg_tax
    
    def print_calculation(self, tax_data: TaxData) -> None:
        """
        Print detailed tax calculation to console.
        
        Args:
            tax_data: Calculated tax data
        """
        print("\n")
        print("╔" + "═" * 90 + "╗")
        print("║" + " TAX LIABILITY CALCULATION ".center(90) + "║")
        print("╠" + "═" * 90 + "╣")
        
        # Step 1: LTCG Exemption
        print("║" + " ".ljust(90) + "║")
        print("║   " + "STEP 1: LTCG EXEMPTION (₹1,25,000 - Section 112A only)".ljust(87) + "║")
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'Indian LTCG Sec 112A (before exemption)'.ljust(50)}₹{tax_data.indian_ltcg:>32,.2f}   ║")
        print(f"║   {'Less: LTCG Exemption'.ljust(50)}₹{tax_data.rebate_used:>32,.2f}   ║")
        print(f"║   {'Indian LTCG (after exemption)'.ljust(50)}₹{tax_data.indian_ltcg_after_rebate:>32,.2f}   ║")
        
        # Step 2: Loss Set-off
        print("║" + " ".ljust(90) + "║")
        print("║   " + "STEP 2: LOSS SET-OFF".ljust(87) + "║")
        print("╟" + "─" * 90 + "╢")
        
        # Show gains and losses before set-off
        print("║   " + "Gains Before Set-off:".ljust(87) + "║")
        print(f"║     {'Foreign LTCG (Schwab)'.ljust(48)}₹{tax_data.foreign_ltcg_gain:>32,.2f}   ║")
        print(f"║     {'Indian LTCG (after exemption)'.ljust(48)}₹{tax_data.indian_ltcg_gain:>32,.2f}   ║")
        print(f"║     {'Foreign STCG (Schwab)'.ljust(48)}₹{tax_data.foreign_stcg_gain:>32,.2f}   ║")
        print(f"║     {'Indian STCG'.ljust(48)}₹{tax_data.indian_stcg_gain:>32,.2f}   ║")
        print("║" + " ".ljust(90) + "║")
        
        # Show losses
        total_ltcg_loss = tax_data.foreign_ltcg_loss + tax_data.indian_ltcg_loss
        total_stcg_loss = tax_data.foreign_stcg_loss + tax_data.indian_stcg_loss
        if total_ltcg_loss > 0 or total_stcg_loss > 0:
            print("║   " + "Losses Before Set-off:".ljust(87) + "║")
            if tax_data.foreign_ltcg_loss > 0:
                print(f"║     {'Foreign LTCG Loss (Schwab)'.ljust(48)}₹{-tax_data.foreign_ltcg_loss:>32,.2f}   ║")
            if tax_data.indian_ltcg_loss > 0:
                print(f"║     {'Indian LTCG Loss'.ljust(48)}₹{-tax_data.indian_ltcg_loss:>32,.2f}   ║")
            if tax_data.foreign_stcg_loss > 0:
                print(f"║     {'Foreign STCG Loss (Schwab)'.ljust(48)}₹{-tax_data.foreign_stcg_loss:>32,.2f}   ║")
            if tax_data.indian_stcg_loss > 0:
                print(f"║     {'Indian STCG Loss'.ljust(48)}₹{-tax_data.indian_stcg_loss:>32,.2f}   ║")
            print("║" + " ".ljust(90) + "║")
        
        # Show set-offs applied
        has_setoffs = (tax_data.stcg_loss_vs_foreign_stcg > 0 or 
                       tax_data.stcg_loss_vs_indian_stcg > 0 or 
                       tax_data.stcg_loss_vs_ltcg > 0 or 
                       tax_data.ltcg_loss_vs_ltcg > 0)
        if has_setoffs:
            print("║   " + "Set-offs Applied:".ljust(87) + "║")
            if tax_data.stcg_loss_vs_foreign_stcg > 0:
                print(f"║     {'STCG Loss → Foreign STCG Gain'.ljust(48)}₹{-tax_data.stcg_loss_vs_foreign_stcg:>32,.2f}   ║")
            if tax_data.stcg_loss_vs_indian_stcg > 0:
                print(f"║     {'STCG Loss → Indian STCG Gain'.ljust(48)}₹{-tax_data.stcg_loss_vs_indian_stcg:>32,.2f}   ║")
            if tax_data.stcg_loss_vs_ltcg > 0:
                print(f"║     {'STCG Loss → LTCG Gain'.ljust(48)}₹{-tax_data.stcg_loss_vs_ltcg:>32,.2f}   ║")
            if tax_data.ltcg_loss_vs_ltcg > 0:
                print(f"║     {'LTCG Loss → LTCG Gain'.ljust(48)}₹{-tax_data.ltcg_loss_vs_ltcg:>32,.2f}   ║")
            print("║" + " ".ljust(90) + "║")
        
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'NET LTCG (Taxable)'.ljust(50)}₹{tax_data.net_ltcg:>32,.2f}   ║")
        print(f"║   {'NET STCG (Taxable)'.ljust(50)}₹{tax_data.net_stcg:>32,.2f}   ║")
        
        # Step 3: Tax Calculation
        print("║" + " ".ljust(90) + "║")
        print("║   " + "STEP 3: TAX CALCULATION".ljust(87) + "║")
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'Foreign LTCG Tax @ 14.95%'.ljust(50)}₹{tax_data.foreign_ltcg_tax:>32,.2f}   ║")
        print(f"║   {'Indian LTCG Tax @ 14.95%'.ljust(50)}₹{tax_data.indian_ltcg_tax:>32,.2f}   ║")
        print(f"║   {'Total LTCG Tax'.ljust(50)}₹{tax_data.ltcg_tax:>32,.2f}   ║")
        print("║" + " ".ljust(90) + "║")
        print(f"║   {'Indian STCG Tax @ 23.92%'.ljust(50)}₹{tax_data.indian_stcg_tax:>32,.2f}   ║")
        print(f"║   {'Foreign STCG Tax @ 39%'.ljust(50)}₹{tax_data.foreign_stcg_tax:>32,.2f}   ║")
        print(f"║   {'Total STCG Tax'.ljust(50)}₹{tax_data.stcg_tax:>32,.2f}   ║")
        print("║" + " ".ljust(90) + "║")
        print(f"║   {'TOTAL TAX'.ljust(50)}₹{tax_data.total_tax:>32,.2f}   ║")
        
        # Step 4: Tax Liability
        print("║" + " ".ljust(90) + "║")
        print("║   " + "STEP 4: TAX LIABILITY".ljust(87) + "║")
        print("╟" + "─" * 90 + "╢")
        print(f"║   {'Total Tax Computed'.ljust(50)}₹{tax_data.total_tax:>32,.2f}   ║")
        print(f"║   {'Less: Taxes Paid Till Date'.ljust(50)}₹{tax_data.taxes_paid:>32,.2f}   ║")
        print("╟" + "─" * 90 + "╢")
        
        if tax_data.tax_liability > 0:
            print(f"║   {'TAX PAYABLE'.ljust(50)}₹{tax_data.tax_liability:>32,.2f}   ║")
        else:
            print(f"║   {'TAX REFUND DUE'.ljust(50)}₹{abs(tax_data.tax_liability):>32,.2f}   ║")
        
        print("║" + " ".ljust(90) + "║")
        print("╚" + "═" * 90 + "╝")

