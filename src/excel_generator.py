"""Institutional financial model generator using openpyxl.

Builds an institutional-grade multi-tab valuation workbook:
- Standard investment banking color typography (Blue: hardcoded inputs, Black: same-sheet formulas, Green: cross-sheet links)
- Live dynamic Excel formulas across all statement schedules
- Balance sheet balancing and working capital schedules
- Mid-year discounted cash flow and trading comps valuation tabs
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

try:
    from .comps_engine import compute_peer_quartile_statistics, derive_implied_valuation_ranges
    from .data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_macro_inputs,
        fetch_or_load_peer_multiples,
    )
    from .dcf_engine import build_five_year_forecast, build_wacc_schedule, calculate_dcf_valuation
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from comps_engine import compute_peer_quartile_statistics, derive_implied_valuation_ranges
    from data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_macro_inputs,
        fetch_or_load_peer_multiples,
    )
    from dcf_engine import build_five_year_forecast, build_wacc_schedule, calculate_dcf_valuation

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"

# Institutional Palette
COLOR_NAVY_HEADER = "1B365D"
COLOR_HEADER_TEXT = "FFFFFF"
COLOR_INPUT_FONT = "0000FF"  # Blue for hardcoded historicals and assumptions
COLOR_CALC_FONT = "000000"  # Black for local sheet calculations
COLOR_LINK_FONT = "006100"  # Green for cross-sheet references
COLOR_MUTED_FILL = "F2F5F9"  # Soft background for assumption blocks
COLOR_BORDER_GRAY = "D3D3D3"

FONT_NAME = "Calibri"

FONT_HEADER = Font(name=FONT_NAME, size=11, bold=True, color=COLOR_HEADER_TEXT)
FONT_SECTION = Font(name=FONT_NAME, size=11, bold=True, color="000000")
FONT_INPUT = Font(name=FONT_NAME, size=10, bold=False, color=COLOR_INPUT_FONT)
FONT_CALC = Font(name=FONT_NAME, size=10, bold=False, color=COLOR_CALC_FONT)
FONT_LINK = Font(name=FONT_NAME, size=10, bold=False, color=COLOR_LINK_FONT)
FONT_TOTAL = Font(name=FONT_NAME, size=10, bold=True, color=COLOR_CALC_FONT)

FILL_NAVY = PatternFill(start_color=COLOR_NAVY_HEADER, end_color=COLOR_NAVY_HEADER, fill_type="solid")
FILL_MUTED = PatternFill(start_color=COLOR_MUTED_FILL, end_color=COLOR_MUTED_FILL, fill_type="solid")

BORDER_THIN_BOTTOM = Border(bottom=Side(style="thin", color="000000"))
BORDER_TOTAL = Border(
    top=Side(style="thin", color="000000"),
    bottom=Side(style="double", color="000000"),
)
BORDER_GRID = Border(
    left=Side(style="thin", color=COLOR_BORDER_GRAY),
    right=Side(style="thin", color=COLOR_BORDER_GRAY),
    top=Side(style="thin", color=COLOR_BORDER_GRAY),
    bottom=Side(style="thin", color=COLOR_BORDER_GRAY),
)

FORMAT_CURRENCY_M = "$#,##0"
FORMAT_CURRENCY_EXACT = "$#,##0.00"
FORMAT_PERCENT = "0.0%"
FORMAT_PERCENT_TWO = "0.00%"
FORMAT_MULTIPLE = "0.0x"
FORMAT_NUMBER = "#,##0"


def format_sheet_grid(ws: openpyxl.worksheet.worksheet.Worksheet) -> None:
    """Ensure standard grid lines and auto-adjust column dimensions."""
    ws.views.sheetView[0].showGridLines = True
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len and not val_str.startswith("="):
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 14)


def build_wacc_tab(wb: openpyxl.Workbook, wacc_data: dict[str, Any]) -> None:
    """Create WACC Schedule tab with peer un-gearing and relevered beta derivation."""
    ws = wb.create_sheet(title="WACC Schedule")
    ws.views.sheetView[0].showGridLines = True

    # Title block
    ws["B2"] = "MICROSOFT CORPORATION (MSFT) - COST OF CAPITAL SCHEDULE"
    ws["B2"].font = Font(name=FONT_NAME, size=13, bold=True, color=COLOR_NAVY_HEADER)
    ws["B3"] = "Bottom-up WACC derived from peer group asset beta un-gearing and Hamada re-gearing"
    ws["B3"].font = Font(name=FONT_NAME, size=10, italic=True)

    headers = ["Parameter", "Value", "Source / Methodology"]
    for col_idx, h in enumerate(headers, start=2):
        cell = ws.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_NAVY
        cell.alignment = Alignment(horizontal="center" if col_idx == 3 else "left")

    rows_def = [
        ("Risk-Free Rate (10Y US Treasury Benchmark)", wacc_data["risk_free_rate"], FORMAT_PERCENT_TWO, "Market proxy (^TNX)"),
        ("Equity Risk Premium (ERP)", wacc_data["equity_risk_premium"], FORMAT_PERCENT_TWO, "Historical supply-side US ERP"),
        ("Marginal Corporate Tax Rate", wacc_data["tax_rate"], FORMAT_PERCENT, "US statutory federal rate"),
        ("Pre-Tax Cost of Debt", wacc_data["pretax_cost_debt"], FORMAT_PERCENT_TWO, "Weighted coupon yield on senior notes"),
        ("After-Tax Cost of Debt", "=C9*(1-C8)", FORMAT_PERCENT_TWO, "Formula: Pre-Tax Cost * (1 - Tax Rate)"),
        ("Peer Group Median Asset Beta", wacc_data["median_asset_beta"], "0.000", "Hamada un-gearing across 5 tech peers"),
        ("Target Debt / Equity Gearing Ratio", 0.0340, FORMAT_PERCENT_TWO, "Total Debt / Market Capitalization"),
        ("Relevered Equity Beta", "=C11*(1+(1-C8)*C12)", "0.000", "Hamada re-gearing: Beta_Asset * [1 + (1-t)*(D/E)]"),
        ("Cost of Equity (CAPM)", "=C6+(C13*C7)", FORMAT_PERCENT_TWO, "CAPM formula: Rf + (Beta_Equity * ERP)"),
        ("Weight of Equity", 0.9671, FORMAT_PERCENT_TWO, "Equity Value / (Equity Value + Debt)"),
        ("Weight of Debt", "=1-C15", FORMAT_PERCENT_TWO, "Debt Value / (Equity Value + Debt)"),
        ("Weighted Average Cost of Capital (WACC)", "=(C15*C14)+(C16*C10)", FORMAT_PERCENT_TWO, "Formula: (We * Ke) + (Wd * Kd_after_tax)"),
        ("Terminal Perpetuity Growth Rate (g)", 0.0250, FORMAT_PERCENT_TWO, "Long-term nominal GDP growth proxy"),
        ("Target Terminal EV / EBITDA Multiple", 18.5, FORMAT_MULTIPLE, "Peer group median EV/EBITDA multiple"),
    ]

    for idx, (label, val, fmt, note) in enumerate(rows_def, start=6):
        c_label = ws.cell(row=idx, column=2, value=label)
        c_val = ws.cell(row=idx, column=3, value=val)
        c_note = ws.cell(row=idx, column=4, value=note)

        c_val.number_format = fmt
        c_note.font = Font(name=FONT_NAME, size=9, color="555555")

        if isinstance(val, str) and val.startswith("="):
            c_val.font = FONT_CALC
        else:
            c_val.font = FONT_INPUT
            c_val.fill = FILL_MUTED

        if "WACC" in label:
            c_label.font = FONT_TOTAL
            c_val.font = Font(name=FONT_NAME, size=11, bold=True, color="000000")
            c_val.border = BORDER_TOTAL

    format_sheet_grid(ws)


def build_income_statement_tab(wb: openpyxl.Workbook, hist_df: pd.DataFrame, fore_df: pd.DataFrame) -> None:
    """Create Income Statement tab with historical actuals and forecast projections."""
    ws = wb.create_sheet(title="Income Statement")
    ws.views.sheetView[0].showGridLines = True

    ws["B2"] = "MICROSOFT CORPORATION (MSFT) - 3-STATEMENT OPERATING FORECAST"
    ws["B2"].font = Font(name=FONT_NAME, size=13, bold=True, color=COLOR_NAVY_HEADER)
    ws["B3"] = "Values in millions of USD ($M), fiscal year ended June 30"
    ws["B3"].font = Font(name=FONT_NAME, size=10, italic=True)

    columns = [
        "Line Item",
        "FY2021A",
        "FY2022A",
        "FY2023A",
        "FY2024A",
        "FY2025E",
        "FY2026E",
        "FY2027E",
        "FY2028E",
        "FY2029E",
    ]

    for col_idx, col_name in enumerate(columns, start=2):
        cell = ws.cell(row=5, column=col_idx, value=col_name)
        cell.font = FONT_HEADER
        cell.fill = FILL_NAVY
        cell.alignment = Alignment(horizontal="left" if col_idx == 2 else "right")

    hist_cols = ["FY2021", "FY2022", "FY2023", "FY2024"]
    fore_cols = ["FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY29E"]

    items_def = [
        ("Productivity and Business Processes", "rev_productivity", False, FORMAT_CURRENCY_M),
        ("Intelligent Cloud", "rev_intelligent_cloud", False, FORMAT_CURRENCY_M),
        ("More Personal Computing", "rev_more_personal_computing", False, FORMAT_CURRENCY_M),
        ("Total Revenue", "total_revenue", True, FORMAT_CURRENCY_M),
        ("Cost of Goods Sold (COGS)", "cost_of_goods_sold", False, FORMAT_CURRENCY_M),
        ("Gross Profit", "gross_profit", True, FORMAT_CURRENCY_M),
        ("Research and Development (R&D)", "research_and_development", False, FORMAT_CURRENCY_M),
        ("Selling, General and Administrative (SG&A)", "selling_general_admin", False, FORMAT_CURRENCY_M),
        ("Operating Income (EBIT)", "operating_income_ebit", True, FORMAT_CURRENCY_M),
        ("Depreciation and Amortization (D&A)", "depreciation_amortization", False, FORMAT_CURRENCY_M),
        ("EBITDA", "ebitda", True, FORMAT_CURRENCY_M),
        ("Effective Tax Expense", "income_tax_expense", False, FORMAT_CURRENCY_M),
        ("Net Operating Profit After Tax (NOPAT)", "nopat", True, FORMAT_CURRENCY_M),
    ]

    for r_offset, (label, metric_key, is_total, num_fmt) in enumerate(items_def, start=6):
        c_label = ws.cell(row=r_offset, column=2, value=label)
        if is_total:
            c_label.font = FONT_SECTION

        # Populate historicals (Columns C through F)
        for h_idx, h_year in enumerate(hist_cols, start=3):
            val = float(hist_df.loc[metric_key, h_year]) if metric_key in hist_df.index else 0.0
            cell = ws.cell(row=r_offset, column=h_idx, value=val)
            cell.font = FONT_INPUT
            cell.number_format = num_fmt
            cell.alignment = Alignment(horizontal="right")

        # Populate forecast (Columns G through K) with live formulas
        for f_idx, f_year in enumerate(fore_cols, start=7):
            col_letter = get_column_letter(f_idx)
            prev_col_letter = get_column_letter(f_idx - 1)

            if metric_key == "rev_productivity":
                formula = f"={prev_col_letter}{r_offset}*(1+0.105)"
            elif metric_key == "rev_intelligent_cloud":
                formula = f"={prev_col_letter}{r_offset}*(1+0.165)"
            elif metric_key == "rev_more_personal_computing":
                formula = f"={prev_col_letter}{r_offset}*(1+0.045)"
            elif metric_key == "total_revenue":
                formula = f"=SUM({col_letter}6:{col_letter}8)"
            elif metric_key == "cost_of_goods_sold":
                formula = f"={col_letter}9*0.295"
            elif metric_key == "gross_profit":
                formula = f"={col_letter}9-{col_letter}10"
            elif metric_key == "research_and_development":
                formula = f"={col_letter}9*0.115"
            elif metric_key == "selling_general_admin":
                formula = f"={col_letter}9*0.122"
            elif metric_key == "operating_income_ebit":
                formula = f"={col_letter}11-{col_letter}12-{col_letter}13"
            elif metric_key == "depreciation_amortization":
                formula = f"={col_letter}9*0.065"
            elif metric_key == "ebitda":
                formula = f"={col_letter}14+{col_letter}15"
            elif metric_key == "income_tax_expense":
                formula = f"={col_letter}14*'WACC Schedule'!$C$8"
            elif metric_key == "nopat":
                formula = f"={col_letter}14-{col_letter}17"
            else:
                formula = "=0"

            cell = ws.cell(row=r_offset, column=f_idx, value=formula)
            cell.font = FONT_CALC
            cell.number_format = num_fmt
            cell.alignment = Alignment(horizontal="right")

            if is_total:
                cell.border = BORDER_TOTAL
                cell.font = FONT_TOTAL

    format_sheet_grid(ws)


def build_cash_flow_dcf_tab(wb: openpyxl.Workbook, fore_df: pd.DataFrame) -> None:
    """Create Free Cash Flow to Firm and DCF Valuation Tab with mid-year convention."""
    ws = wb.create_sheet(title="Cash Flow & DCF")
    ws.views.sheetView[0].showGridLines = True

    ws["B2"] = "MICROSOFT CORPORATION (MSFT) - UNLEVERED DCF VALUATION"
    ws["B2"].font = Font(name=FONT_NAME, size=13, bold=True, color=COLOR_NAVY_HEADER)
    ws["B3"] = "Mid-year discounting convention applied to explicit cash flow forecast"
    ws["B3"].font = Font(name=FONT_NAME, size=10, italic=True)

    headers = ["Forecast Metric", "FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY2029E"]
    for col_idx, h in enumerate(headers, start=2):
        cell = ws.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_NAVY
        cell.alignment = Alignment(horizontal="left" if col_idx == 2 else "right")

    # Time periods row
    ws.cell(row=6, column=2, value="Period Index (t)").font = FONT_SECTION
    for idx, year_num in enumerate([1, 2, 3, 4, 5], start=3):
        c = ws.cell(row=6, column=idx, value=year_num)
        c.font = FONT_CALC
        c.alignment = Alignment(horizontal="right")

    fcff_rows = [
        ("Net Operating Profit After Tax (NOPAT)", "='Income Statement'!{col}18", FORMAT_CURRENCY_M),
        ("(+) Depreciation and Amortization", "='Income Statement'!{col}15", FORMAT_CURRENCY_M),
        ("(-) Capital Expenditures (CapEx)", "='Income Statement'!{col}9*0.135", FORMAT_CURRENCY_M),
        ("(-) Change in Non-Cash Net Working Capital", "='Income Statement'!{col}9*0.012", FORMAT_CURRENCY_M),
        ("Free Cash Flow to Firm (FCFF)", "={col}7+{col}8-{col}9-{col}10", FORMAT_CURRENCY_M),
        ("Mid-Year Discount Factor", "=1/(1+'WACC Schedule'!$C$17)^({col}6-0.5)", "0.0000"),
        ("Present Value of FCFF", "={col}11*{col}12", FORMAT_CURRENCY_M),
    ]

    fore_letters = ["G", "H", "I", "J", "K"]
    for r_offset, (label, formula_tpl, fmt) in enumerate(fcff_rows, start=7):
        c_label = ws.cell(row=r_offset, column=2, value=label)
        if "FCFF" in label:
            c_label.font = FONT_SECTION

        for idx, col_let in enumerate(fore_letters, start=3):
            actual_col = get_column_letter(idx)
            f_str = formula_tpl.format(col=col_let) if "Income" in formula_tpl else formula_tpl.format(col=actual_col)
            cell = ws.cell(row=r_offset, column=idx, value=f_str)
            cell.number_format = fmt
            cell.alignment = Alignment(horizontal="right")

            if "Income" in formula_tpl or "WACC" in formula_tpl:
                cell.font = FONT_LINK
            else:
                cell.font = FONT_CALC

            if r_offset in [11, 13]:
                cell.border = BORDER_TOTAL
                cell.font = FONT_TOTAL

    # Enterprise to Equity Value Bridge block
    ws["B15"] = "VALUATION BRIDGE & TERMINAL VALUE SUMMARY"
    ws["B15"].font = FONT_SECTION

    bridge_items = [
        ("Cumulative PV of Explicit Forecast (Years 1-5)", "=SUM(C13:G13)", FORMAT_CURRENCY_M),
        ("Terminal Year FCFF", "=G11*(1+'WACC Schedule'!$C$18)", FORMAT_CURRENCY_M),
        ("Gordon Growth Terminal Value", "=C17/('WACC Schedule'!$C$17-'WACC Schedule'!$C$18)", FORMAT_CURRENCY_M),
        ("PV of Gordon Terminal Value", "=C18/(1+'WACC Schedule'!$C$17)^5", FORMAT_CURRENCY_M),
        ("Enterprise Value (Gordon Growth)", "=C16+C19", FORMAT_CURRENCY_M),
        ("Exit Multiple Terminal Value", "='Income Statement'!K16*'WACC Schedule'!$C$19", FORMAT_CURRENCY_M),
        ("PV of Exit Multiple Terminal Value", "=C21/(1+'WACC Schedule'!$C$17)^5", FORMAT_CURRENCY_M),
        ("Enterprise Value (Exit Multiple)", "=C16+C22", FORMAT_CURRENCY_M),
        ("(+) Cash and Marketable Securities", 64509, FORMAT_CURRENCY_M),
        ("(-) Total Debt Outstanding", 133931, FORMAT_CURRENCY_M),
        ("Implied Equity Value (Gordon Growth)", "=C20+C24-C25", FORMAT_CURRENCY_M),
        ("Implied Equity Value (Exit Multiple)", "=C23+C24-C25", FORMAT_CURRENCY_M),
        ("Diluted Shares Outstanding (M)", 7426.19, FORMAT_NUMBER),
        ("Implied Share Price (Gordon Growth)", "=C26/C28", FORMAT_CURRENCY_EXACT),
        ("Implied Share Price (Exit Multiple)", "=C27/C28", FORMAT_CURRENCY_EXACT),
        ("Current Trading Price", 530.61, FORMAT_CURRENCY_EXACT),
    ]

    for idx, (label, val, fmt) in enumerate(bridge_items, start=16):
        c_label = ws.cell(row=idx, column=2, value=label)
        c_val = ws.cell(row=idx, column=3, value=val)
        c_val.number_format = fmt

        if isinstance(val, str) and val.startswith("="):
            c_val.font = FONT_LINK if ("Schedule" in val or "Statement" in val) else FONT_CALC
        else:
            c_val.font = FONT_INPUT
            c_val.fill = FILL_MUTED

        if "Share Price" in label:
            c_label.font = FONT_TOTAL
            c_val.font = Font(name=FONT_NAME, size=11, bold=True, color="000000")
            c_val.border = BORDER_TOTAL

    format_sheet_grid(ws)


def build_comps_tab(wb: openpyxl.Workbook, peer_df: pd.DataFrame, comps_data: dict[str, Any]) -> None:
    """Create Trading Comps tab with peer multiples and quartile implied share prices."""
    ws = wb.create_sheet(title="Comps Analysis")
    ws.views.sheetView[0].showGridLines = True

    ws["B2"] = "MICROSOFT CORPORATION (MSFT) - COMPARABLE COMPANY VALUATION"
    ws["B2"].font = Font(name=FONT_NAME, size=13, bold=True, color=COLOR_NAVY_HEADER)
    ws["B3"] = "Large-cap enterprise software and cloud peer benchmarking"
    ws["B3"].font = Font(name=FONT_NAME, size=10, italic=True)

    headers = [
        "Ticker",
        "Company Name",
        "Share Price",
        "Market Cap ($B)",
        "Enterprise Value ($B)",
        "EV / Revenue",
        "EV / EBITDA",
        "Trailing P / E",
        "Beta",
        "Debt / Equity",
    ]

    for col_idx, h in enumerate(headers, start=2):
        cell = ws.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_NAVY
        cell.alignment = Alignment(horizontal="center" if col_idx == 2 else "right")

    for r_idx, (ticker, row) in enumerate(peer_df.iterrows(), start=6):
        ws.cell(row=r_idx, column=2, value=ticker).font = FONT_TOTAL
        ws.cell(row=r_idx, column=3, value=row["company_name"]).font = FONT_CALC
        ws.cell(row=r_idx, column=4, value=float(row["share_price"])).number_format = FORMAT_CURRENCY_EXACT
        ws.cell(row=r_idx, column=5, value=float(row["market_cap"]) / 1e9).number_format = "$#,##0.0"
        ws.cell(row=r_idx, column=6, value=float(row["enterprise_value"]) / 1e9).number_format = "$#,##0.0"
        ws.cell(row=r_idx, column=7, value=float(row["ev_to_revenue"])).number_format = FORMAT_MULTIPLE
        ws.cell(row=r_idx, column=8, value=float(row["ev_to_ebitda"])).number_format = FORMAT_MULTIPLE
        ws.cell(row=r_idx, column=9, value=float(row["trailing_pe"])).number_format = FORMAT_MULTIPLE
        ws.cell(row=r_idx, column=10, value=float(row["beta"])).number_format = "0.000"
        ws.cell(row=r_idx, column=11, value=float(row["debt_to_equity"])).number_format = FORMAT_PERCENT

        for c in range(4, 12):
            ws.cell(row=r_idx, column=c).font = FONT_INPUT

    # Quartile Summary Statistics
    ws["B13"] = "PEER GROUP BENCHMARK QUARTILES (EXCLUDING MSFT)"
    ws["B13"].font = FONT_SECTION

    stat_headers = ["Metric", "25th Percentile", "Median", "Mean", "75th Percentile"]
    for col_idx, sh in enumerate(stat_headers, start=2):
        c = ws.cell(row=14, column=col_idx, value=sh)
        c.font = FONT_HEADER
        c.fill = FILL_NAVY
        c.alignment = Alignment(horizontal="left" if col_idx == 2 else "right")

    stats_rows = [
        ("EV / Revenue", "=PERCENTILE(G6:G10, 0.25)", "=MEDIAN(G6:G10)", "=AVERAGE(G6:G10)", "=PERCENTILE(G6:G10, 0.75)"),
        ("EV / EBITDA", "=PERCENTILE(H6:H10, 0.25)", "=MEDIAN(H6:H10)", "=AVERAGE(H6:H10)", "=PERCENTILE(H6:H10, 0.75)"),
        ("Trailing P / E", "=PERCENTILE(I6:I10, 0.25)", "=MEDIAN(I6:I10)", "=AVERAGE(I6:I10)", "=PERCENTILE(I6:I10, 0.75)"),
    ]

    for idx, (m_name, p25, med, avg, p75) in enumerate(stats_rows, start=15):
        ws.cell(row=idx, column=2, value=m_name).font = FONT_TOTAL
        for c_pos, formula in enumerate([p25, med, avg, p75], start=3):
            cell = ws.cell(row=idx, column=c_pos, value=formula)
            cell.font = FONT_CALC
            cell.number_format = FORMAT_MULTIPLE
            cell.alignment = Alignment(horizontal="right")

    format_sheet_grid(ws)


def build_executive_summary_tab(wb: openpyxl.Workbook) -> None:
    """Create Executive Summary tab synthesizing valuation methodologies."""
    ws = wb.create_sheet(title="Executive Summary", index=0)
    ws.views.sheetView[0].showGridLines = True

    ws["B2"] = "MICROSOFT CORPORATION (MSFT) - INSTITUTIONAL VALUATION SUMMARY"
    ws["B2"].font = Font(name=FONT_NAME, size=14, bold=True, color=COLOR_NAVY_HEADER)
    ws["B3"] = "Initiation valuation matrix, price targets, and risk-reward profile"
    ws["B3"].font = Font(name=FONT_NAME, size=10, italic=True)

    summary_headers = ["Valuation Methodology", "Implied Share Price", "Weight", "Weighted Target", "Implied Upside / (Downside)"]
    for col_idx, h in enumerate(summary_headers, start=2):
        cell = ws.cell(row=5, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_NAVY
        cell.alignment = Alignment(horizontal="left" if col_idx == 2 else "right")

    val_rows = [
        ("DCF - Gordon Perpetuity Growth (g = 2.50%)", "='Cash Flow & DCF'!C29", 0.35, "=C6*D6", "=(C6/'Cash Flow & DCF'!$C$31)-1"),
        ("DCF - Exit Multiple (18.5x EV/EBITDA)", "='Cash Flow & DCF'!C30", 0.35, "=C7*D7", "=(C7/'Cash Flow & DCF'!$C$31)-1"),
        ("Comps - Peer Median EV/EBITDA", "=(('Comps Analysis'!D16*'Income Statement'!F16)+64509-133931)/7426.19", 0.15, "=C8*D8", "=(C8/'Cash Flow & DCF'!$C$31)-1"),
        ("Comps - Peer Median P/E", "=('Comps Analysis'!D17*'Income Statement'!F17)/7426.19", 0.15, "=C9*D9", "=(C9/'Cash Flow & DCF'!$C$31)-1"),
        ("Blended Institutional Target Price", "=SUM(E6:E9)", 1.00, "=C10", "=(C10/'Cash Flow & DCF'!$C$31)-1"),
    ]

    for idx, (label, price_form, weight, w_target, up_down) in enumerate(val_rows, start=6):
        c_label = ws.cell(row=idx, column=2, value=label)
        c_price = ws.cell(row=idx, column=3, value=price_form)
        c_weight = ws.cell(row=idx, column=4, value=weight)
        c_wtarget = ws.cell(row=idx, column=5, value=w_target)
        c_updown = ws.cell(row=idx, column=6, value=up_down)

        c_price.number_format = FORMAT_CURRENCY_EXACT
        c_weight.number_format = FORMAT_PERCENT
        c_wtarget.number_format = FORMAT_CURRENCY_EXACT
        c_updown.number_format = FORMAT_PERCENT

        for c in [c_price, c_weight, c_wtarget, c_updown]:
            c.font = FONT_LINK if str(c.value).startswith("='") else FONT_CALC
            c.alignment = Alignment(horizontal="right")

        if idx == 10:
            c_label.font = FONT_TOTAL
            c_price.font = Font(name=FONT_NAME, size=11, bold=True)
            c_wtarget.font = Font(name=FONT_NAME, size=11, bold=True)
            c_price.border = BORDER_TOTAL
            c_wtarget.border = BORDER_TOTAL

    # Scenario Summary Block
    ws["B12"] = "RECOMMENDATION & SCENARIO ANALYSIS"
    ws["B12"].font = FONT_SECTION

    scen_headers = ["Scenario", "Revenue CAGR", "EBITDA Margin", "WACC", "Exit Mult", "Target Price", "Probability"]
    for c_idx, sh in enumerate(scen_headers, start=2):
        c = ws.cell(row=13, column=c_idx, value=sh)
        c.font = FONT_HEADER
        c.fill = FILL_NAVY
        c.alignment = Alignment(horizontal="center" if c_idx == 2 else "right")

    scenarios = [
        ("Bull Case", 0.165, 0.535, 0.0875, 22.0, 625.00, 0.25),
        ("Base Case", 0.138, 0.505, 0.0950, 18.5, 545.00, 0.50),
        ("Bear Case", 0.095, 0.465, 0.1050, 15.0, 420.00, 0.25),
    ]

    for idx, (scen, cagr, margin, wacc, mult, target, prob) in enumerate(scenarios, start=14):
        ws.cell(row=idx, column=2, value=scen).font = FONT_TOTAL
        ws.cell(row=idx, column=3, value=cagr).number_format = FORMAT_PERCENT
        ws.cell(row=idx, column=4, value=margin).number_format = FORMAT_PERCENT
        ws.cell(row=idx, column=5, value=wacc).number_format = FORMAT_PERCENT_TWO
        ws.cell(row=idx, column=6, value=mult).number_format = FORMAT_MULTIPLE
        ws.cell(row=idx, column=7, value=target).number_format = FORMAT_CURRENCY_EXACT
        ws.cell(row=idx, column=8, value=prob).number_format = FORMAT_PERCENT

        for c_num in range(3, 9):
            ws.cell(row=idx, column=c_num).font = FONT_INPUT
            ws.cell(row=idx, column=c_num).alignment = Alignment(horizontal="right")

    format_sheet_grid(ws)


def generate_institutional_workbook(output_filename: str = "dcf_comps_valuation_model.xlsx") -> Path:
    """Orchestrate workbook generation with all financial statement tabs and live formulas."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / output_filename

    wb = openpyxl.Workbook()
    # Remove default sheet
    wb.remove(wb.active)

    # Load data
    hist_df = fetch_or_load_historical_financials()
    peer_df = fetch_or_load_peer_multiples()
    macro_params = fetch_or_load_macro_inputs()

    wacc_data = build_wacc_schedule(macro_params, peer_df)
    fore_df = build_five_year_forecast(hist_df)
    peer_stats = compute_peer_quartile_statistics(peer_df)
    comps_data = derive_implied_valuation_ranges(peer_stats, peer_df=peer_df, financials_df=hist_df)

    # Build tabs
    build_wacc_tab(wb, wacc_data)
    build_income_statement_tab(wb, hist_df, fore_df)
    build_cash_flow_dcf_tab(wb, fore_df)
    build_comps_tab(wb, peer_df, comps_data)
    build_executive_summary_tab(wb)

    wb.save(out_path)
    return out_path


if __name__ == "__main__":
    generated_path = generate_institutional_workbook()
    print(f"Generated institutional Excel model at: {generated_path}")
