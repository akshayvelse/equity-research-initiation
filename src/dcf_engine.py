"""Discounted Cash Flow (DCF) valuation engine with mid-year convention.

Builds an explicit 5-year 3-statement operating forecast, computes bottom-up
WACC via peer Hamada asset-beta un-gearing and re-gearing, derives terminal value
under both Gordon Growth and Exit Multiple methods, and outputs 2D sensitivity matrices.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from .data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_macro_inputs,
        fetch_or_load_peer_multiples,
    )
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_macro_inputs,
        fetch_or_load_peer_multiples,
    )

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def build_wacc_schedule(
    macro_params: dict[str, float] | None = None,
    peer_multiples: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Calculate bottom-up WACC using peer asset beta un-gearing and re-gearing.

    Hamada formula:
        beta_asset = beta_equity / [1 + (1 - tax_rate) * (Debt / Equity)]
        beta_equity_target = median(beta_asset) * [1 + (1 - tax_rate) * (Target_Debt / Target_Equity)]
    """
    if macro_params is None:
        macro_params = fetch_or_load_macro_inputs()
    if peer_multiples is None:
        peer_multiples = fetch_or_load_peer_multiples()

    rf = macro_params["risk_free_rate"]
    erp = macro_params["equity_risk_premium"]
    tax_rate = macro_params["marginal_tax_rate"]
    pretax_cost_debt = macro_params["effective_pretax_debt_cost"]

    # Calculate asset beta for each peer
    peer_betas = []
    for ticker, row in peer_multiples.iterrows():
        b_equity = float(row["beta"])
        d_e = float(row["debt_to_equity"])
        b_asset = b_equity / (1.0 + (1.0 - tax_rate) * d_e)
        peer_betas.append(b_asset)

    median_asset_beta = float(np.median(peer_betas))

    # Target company capital structure
    target_row = peer_multiples.loc["MSFT"]
    target_d_e = float(target_row["debt_to_equity"])
    relevered_equity_beta = median_asset_beta * (1.0 + (1.0 - tax_rate) * target_d_e)

    # Capital asset pricing model for cost of equity
    cost_of_equity = rf + relevered_equity_beta * erp

    # After-tax cost of debt
    after_tax_cost_debt = pretax_cost_debt * (1.0 - tax_rate)

    # Weights
    debt_val = float(target_row["total_debt"])
    equity_val = float(target_row["market_cap"])
    total_val = debt_val + equity_val

    weight_equity = equity_val / total_val if total_val > 0 else 0.95
    weight_debt = debt_val / total_val if total_val > 0 else 0.05

    wacc = (weight_equity * cost_of_equity) + (weight_debt * after_tax_cost_debt)

    return {
        "risk_free_rate": rf,
        "equity_risk_premium": erp,
        "tax_rate": tax_rate,
        "pretax_cost_debt": pretax_cost_debt,
        "after_tax_cost_debt": after_tax_cost_debt,
        "median_asset_beta": median_asset_beta,
        "relevered_equity_beta": relevered_equity_beta,
        "cost_of_equity": cost_of_equity,
        "weight_equity": weight_equity,
        "weight_debt": weight_debt,
        "wacc": wacc,
    }


def build_five_year_forecast(
    historical_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Project 5-year explicit operating statements (FY25E - FY29E) in millions of USD.

    Models granular segment growth, fixed-cost operating scale efficiencies,
    capital expenditure intensity cycles, and balance sheet working capital schedules.
    """
    if historical_df is None:
        historical_df = fetch_or_load_historical_financials()

    # Base FY24 actuals ($M)
    base_prod = float(historical_df.loc["rev_productivity", "FY2024"])
    base_cloud = float(historical_df.loc["rev_intelligent_cloud", "FY2024"])
    base_mpc = float(historical_df.loc["rev_more_personal_computing", "FY2024"])

    forecast_years = ["FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY29E"]

    # Segment growth trajectories
    prod_growth = [0.115, 0.105, 0.095, 0.090, 0.085]
    cloud_growth = [0.185, 0.170, 0.155, 0.140, 0.125]
    mpc_growth = [0.055, 0.050, 0.045, 0.040, 0.035]

    # Operating parameters
    cogs_margin = [0.298, 0.295, 0.292, 0.290, 0.288]
    rd_margin = [0.118, 0.116, 0.114, 0.112, 0.110]
    sga_margin = [0.128, 0.125, 0.122, 0.120, 0.118]
    da_margin = [0.068, 0.066, 0.065, 0.064, 0.062]
    capex_margin = [0.175, 0.160, 0.140, 0.125, 0.115]

    # Working capital days assumptions
    dso = 56.0  # Days Sales Outstanding for Accounts Receivable
    dio = 15.0  # Days Inventory Outstanding
    dpo = 48.0  # Days Payable Outstanding against COGS + Opex
    tax_rate = 0.210

    data: dict[str, list[float]] = {
        "rev_productivity": [],
        "rev_intelligent_cloud": [],
        "rev_more_personal_computing": [],
        "total_revenue": [],
        "cogs": [],
        "gross_profit": [],
        "rd_expense": [],
        "sga_expense": [],
        "ebit": [],
        "da": [],
        "ebitda": [],
        "tax_on_ebit": [],
        "nopat": [],
        "capex": [],
        "accounts_receivable": [],
        "inventories": [],
        "accounts_payable": [],
        "net_working_capital": [],
        "change_in_nwc": [],
        "fcff": [],
    }

    curr_prod = base_prod
    curr_cloud = base_cloud
    curr_mpc = base_mpc
    prev_nwc = float(historical_df.loc["net_working_capital", "FY2024"])

    for i in range(5):
        curr_prod *= 1.0 + prod_growth[i]
        curr_cloud *= 1.0 + cloud_growth[i]
        curr_mpc *= 1.0 + mpc_growth[i]
        rev = curr_prod + curr_cloud + curr_mpc

        cogs = rev * cogs_margin[i]
        gp = rev - cogs
        rd = rev * rd_margin[i]
        sga = rev * sga_margin[i]
        ebit = gp - rd - sga
        da = rev * da_margin[i]
        ebitda = ebit + da
        tax = ebit * tax_rate
        nopat = ebit - tax
        capex = rev * capex_margin[i]

        ar = (rev * dso) / 365.0
        inv = (cogs * dio) / 365.0
        ap = ((cogs + rd + sga) * dpo) / 365.0
        nwc = ar + inv - ap
        delta_nwc = nwc - prev_nwc
        prev_nwc = nwc

        # Free Cash Flow to Firm = NOPAT + D&A - CapEx - Delta NWC
        fcff = nopat + da - capex - delta_nwc

        data["rev_productivity"].append(curr_prod)
        data["rev_intelligent_cloud"].append(curr_cloud)
        data["rev_more_personal_computing"].append(curr_mpc)
        data["total_revenue"].append(rev)
        data["cogs"].append(cogs)
        data["gross_profit"].append(gp)
        data["rd_expense"].append(rd)
        data["sga_expense"].append(sga)
        data["ebit"].append(ebit)
        data["da"].append(da)
        data["ebitda"].append(ebitda)
        data["tax_on_ebit"].append(tax)
        data["nopat"].append(nopat)
        data["capex"].append(capex)
        data["accounts_receivable"].append(ar)
        data["inventories"].append(inv)
        data["accounts_payable"].append(ap)
        data["net_working_capital"].append(nwc)
        data["change_in_nwc"].append(delta_nwc)
        data["fcff"].append(fcff)

    return pd.DataFrame(data, index=forecast_years).T


def calculate_dcf_valuation(
    forecast_df: pd.DataFrame,
    wacc_schedule: dict[str, Any],
    macro_params: dict[str, float] | None = None,
    peer_multiples: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Discount explicit cash flows with mid-year convention and derive terminal values.

    Applies mid-year discount factors:
        DF_t = (1 + WACC)^(-(t - 0.5)) for explicit forecast years t in 1..5.
    Terminal value discounted to t=0 from horizon t=5:
        PV(TV) = TV / (1 + WACC)^5
    """
    if macro_params is None:
        macro_params = fetch_or_load_macro_inputs()
    if peer_multiples is None:
        peer_multiples = fetch_or_load_peer_multiples()

    wacc = wacc_schedule["wacc"]
    g = macro_params["terminal_growth_rate"]
    exit_multiple = macro_params["target_exit_multiple"]

    fcff_series = forecast_df.loc["fcff"].values
    ebitda_series = forecast_df.loc["ebitda"].values

    # Mid-year convention discount factors
    years = np.array([1, 2, 3, 4, 5])
    mid_year_discount_factors = 1.0 / np.power(1.0 + wacc, years - 0.5)
    pv_fcff = fcff_series * mid_year_discount_factors
    cumulative_pv_fcff = float(np.sum(pv_fcff))

    # Terminal Value: Gordon Growth
    final_fcff = fcff_series[-1]
    tv_gordon = (final_fcff * (1.0 + g)) / (wacc - g)
    pv_tv_gordon = tv_gordon / np.power(1.0 + wacc, 5.0)
    ev_gordon = cumulative_pv_fcff + pv_tv_gordon

    # Terminal Value: Exit Multiple
    final_ebitda = ebitda_series[-1]
    tv_exit = final_ebitda * exit_multiple
    pv_tv_exit = tv_exit / np.power(1.0 + wacc, 5.0)
    ev_exit = cumulative_pv_fcff + pv_tv_exit

    # Balance sheet adjustments for equity value bridge (converted to $M to match forecast)
    target_row = peer_multiples.loc["MSFT"]
    cash_val = float(target_row["total_cash"]) / 1e6
    debt_val = float(target_row["total_debt"]) / 1e6
    shares_out = (float(target_row["market_cap"]) / float(target_row["share_price"])) / 1e6

    # Implied equity values in $M and share prices in USD
    equity_val_gordon = ev_gordon + cash_val - debt_val
    price_gordon = equity_val_gordon / shares_out

    equity_val_exit = ev_exit + cash_val - debt_val
    price_exit = equity_val_exit / shares_out

    # Blended valuation (50% Gordon Growth, 50% Exit Multiple)
    blended_ev = 0.5 * ev_gordon + 0.5 * ev_exit
    blended_equity = blended_ev + cash_val - debt_val
    blended_price = blended_equity / shares_out

    return {
        "wacc": wacc,
        "terminal_growth_rate": g,
        "exit_multiple": exit_multiple,
        "cash_balance": cash_val,
        "total_debt": debt_val,
        "net_debt": debt_val - cash_val,
        "shares_outstanding": shares_out,
        "current_market_price": float(target_row["share_price"]),
        "cumulative_pv_fcff": cumulative_pv_fcff,
        "tv_gordon": tv_gordon,
        "pv_tv_gordon": pv_tv_gordon,
        "ev_gordon": ev_gordon,
        "equity_val_gordon": equity_val_gordon,
        "price_gordon": price_gordon,
        "tv_exit": tv_exit,
        "pv_tv_exit": pv_tv_exit,
        "ev_exit": ev_exit,
        "equity_val_exit": equity_val_exit,
        "price_exit": price_exit,
        "blended_ev": blended_ev,
        "blended_equity": blended_equity,
        "blended_price": blended_price,
        "mid_year_discount_factors": mid_year_discount_factors.tolist(),
        "pv_fcff_series": pv_fcff.tolist(),
    }


def generate_sensitivity_matrix(
    forecast_df: pd.DataFrame,
    wacc_schedule: dict[str, Any],
    macro_params: dict[str, float] | None = None,
    peer_multiples: pd.DataFrame | None = None,
    wacc_delta_bps: int = 150,
    g_delta_bps: int = 100,
) -> pd.DataFrame:
    """Generate 2D implied share price matrix across WACC and Terminal Growth Rate."""
    if macro_params is None:
        macro_params = fetch_or_load_macro_inputs()
    if peer_multiples is None:
        peer_multiples = fetch_or_load_peer_multiples()

    base_wacc = wacc_schedule["wacc"]
    base_g = macro_params["terminal_growth_rate"]

    target_row = peer_multiples.loc["MSFT"]
    cash_val = float(target_row["total_cash"]) / 1e6
    debt_val = float(target_row["total_debt"]) / 1e6
    shares_out = (float(target_row["market_cap"]) / float(target_row["share_price"])) / 1e6

    fcff_series = forecast_df.loc["fcff"].values
    final_fcff = fcff_series[-1]
    years = np.array([1, 2, 3, 4, 5])

    wacc_steps = np.linspace(
        base_wacc - (wacc_delta_bps / 10000.0),
        base_wacc + (wacc_delta_bps / 10000.0),
        7,
    )
    g_steps = np.linspace(
        base_g - (g_delta_bps / 10000.0),
        base_g + (g_delta_bps / 10000.0),
        5,
    )

    matrix = np.zeros((len(g_steps), len(wacc_steps)))

    for i, g in enumerate(g_steps):
        for j, w in enumerate(wacc_steps):
            if w <= g:
                matrix[i, j] = np.nan
                continue
            dfs = 1.0 / np.power(1.0 + w, years - 0.5)
            pv_cash = np.sum(fcff_series * dfs)
            tv = (final_fcff * (1.0 + g)) / (w - g)
            pv_tv = tv / np.power(1.0 + w, 5.0)
            ev = pv_cash + pv_tv
            eq = ev + cash_val - debt_val
            matrix[i, j] = eq / shares_out

    row_labels = [f"g = {g*100:.2f}%" for g in g_steps]
    col_labels = [f"WACC = {w*100:.2f}%" for w in wacc_steps]

    return pd.DataFrame(matrix, index=row_labels, columns=col_labels)


def plot_sensitivity_surface(sensitivity_df: pd.DataFrame, output_path: Path) -> None:
    """Render and save publication-grade 2D sensitivity heatmap."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 6), dpi=300)
    data = sensitivity_df.values

    cax = ax.imshow(data, cmap="YlGnBu", aspect="auto")

    ax.set_xticks(np.arange(len(sensitivity_df.columns)))
    ax.set_yticks(np.arange(len(sensitivity_df.index)))
    ax.set_xticklabels(sensitivity_df.columns, fontsize=9, fontweight="bold")
    ax.set_yticklabels(sensitivity_df.index, fontsize=9, fontweight="bold")

    plt.setp(ax.get_xticklabels(), rotation=30, ha="right", rotation_mode="anchor")

    # Cell values formatting
    for i in range(len(sensitivity_df.index)):
        for j in range(len(sensitivity_df.columns)):
            val = data[i, j]
            text = f"${val:.2f}" if not np.isnan(val) else "N/A"
            ax.text(
                j,
                i,
                text,
                ha="center",
                va="center",
                color="black" if val < np.nanmean(data) * 1.05 else "white",
                fontsize=9,
            )

    ax.set_title(
        "MSFT Implied Share Price Sensitivity Matrix\nWACC vs Terminal Growth Rate (Perpetuity Method)",
        fontsize=12,
        fontweight="bold",
        pad=15,
    )

    cbar = fig.colorbar(cax, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.set_ylabel("Implied Share Price (USD)", rotation=-90, va="bottom", fontsize=10)

    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


if __name__ == "__main__":
    wacc_sched = build_wacc_schedule()
    forecast = build_five_year_forecast()
    valuation = calculate_dcf_valuation(forecast, wacc_sched)
    sensitivity = generate_sensitivity_matrix(forecast, wacc_sched)
    plot_sensitivity_surface(sensitivity, OUTPUT_DIR / "sensitivity_surface.png")

    print(f"Calculated WACC: {wacc_sched['wacc']*100:.2f}%")
    print(f"Gordon Growth Implied Price: ${valuation['price_gordon']:.2f}")
    print(f"Exit Multiple Implied Price: ${valuation['price_exit']:.2f}")
    print(f"Blended Implied Price: ${valuation['blended_price']:.2f}")
    print(f"Current Market Price: ${valuation['current_market_price']:.2f}")
