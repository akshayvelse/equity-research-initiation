"""Unit and integration test suite for DCF and comparable company valuation engines."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Ensure local src directory is on sys.path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from comps_engine import compute_peer_quartile_statistics, derive_implied_valuation_ranges
from data_loader import (
    fetch_or_load_historical_financials,
    fetch_or_load_macro_inputs,
    fetch_or_load_peer_multiples,
)
from dcf_engine import (
    build_five_year_forecast,
    build_wacc_schedule,
    calculate_dcf_valuation,
    generate_sensitivity_matrix,
)


def test_historical_financials_integrity() -> None:
    """Verify historical SEC balance sheet and income statement accounting consistency."""
    hist = fetch_or_load_historical_financials()

    for yr in ["FY2021", "FY2022", "FY2023", "FY2024"]:
        prod = float(hist.loc["rev_productivity", yr])
        cloud = float(hist.loc["rev_intelligent_cloud", yr])
        mpc = float(hist.loc["rev_more_personal_computing", yr])
        total = float(hist.loc["total_revenue", yr])
        assert abs((prod + cloud + mpc) - total) < 1.0, f"Segment revenue sum mismatch in {yr}"

        cogs = float(hist.loc["cost_of_goods_sold", yr])
        gp = float(hist.loc["gross_profit", yr])
        assert abs((total - cogs) - gp) < 1.0, f"Gross profit identity violated in {yr}"

        ar = float(hist.loc["accounts_receivable", yr])
        inv = float(hist.loc["inventories", yr])
        ap = float(hist.loc["accounts_payable_accrued", yr])
        nwc = float(hist.loc["net_working_capital", yr])
        assert abs((ar + inv - ap) - nwc) < 1.0, f"NWC identity violated in {yr}"


def test_wacc_calculation_bounds() -> None:
    """Verify bottom-up WACC derivation adheres to capital asset pricing boundaries."""
    macro = fetch_or_load_macro_inputs()
    peers = fetch_or_load_peer_multiples()
    wacc_sched = build_wacc_schedule(macro, peers)

    wacc = wacc_sched["wacc"]
    cost_of_equity = wacc_sched["cost_of_equity"]
    after_tax_debt = wacc_sched["after_tax_cost_debt"]

    assert after_tax_debt < wacc < cost_of_equity, "WACC must be bounded by cost of debt and cost of equity"
    assert 0.065 <= wacc <= 0.115, f"WACC {wacc:.4f} outside institutional boundaries"
    assert abs((wacc_sched["weight_equity"] + wacc_sched["weight_debt"]) - 1.0) < 1e-6


def test_five_year_forecast_and_fcff() -> None:
    """Verify operational projections and positive Free Cash Flow to Firm generation."""
    hist = fetch_or_load_historical_financials()
    forecast = build_five_year_forecast(hist)

    assert forecast.shape[1] == 5, "Forecast must span exactly 5 explicit projection years"

    for col in forecast.columns:
        rev = float(forecast.loc["total_revenue", col])
        ebitda = float(forecast.loc["ebitda", col])
        fcff = float(forecast.loc["fcff", col])
        assert rev > 0, f"Negative projected revenue in {col}"
        assert ebitda > 0, f"Negative projected EBITDA in {col}"
        assert fcff > 0, f"Negative projected FCFF in {col}"

    for col in forecast.columns:
        nopat = float(forecast.loc["nopat", col])
        da = float(forecast.loc["da", col])
        capex = float(forecast.loc["capex", col])
        dnwc = float(forecast.loc["change_in_nwc", col])
        fcff = float(forecast.loc["fcff", col])
        expected_fcff = nopat + da - capex - dnwc
        assert abs(fcff - expected_fcff) < 1e-4, f"FCFF accounting identity failed in {col}"


def test_dcf_valuation_bridge_identity() -> None:
    """Verify enterprise value to equity value bridge and per-share pricing math."""
    hist = fetch_or_load_historical_financials()
    peers = fetch_or_load_peer_multiples()
    macro = fetch_or_load_macro_inputs()

    wacc_sched = build_wacc_schedule(macro, peers)
    forecast = build_five_year_forecast(hist)
    val = calculate_dcf_valuation(forecast, wacc_sched, macro, peers)

    ev_g = val["ev_gordon"]
    eq_g = val["equity_val_gordon"]
    cash = val["cash_balance"]
    debt = val["total_debt"]
    assert abs((ev_g + cash - debt) - eq_g) < 1e-4, "Gordon Equity Value bridge identity failed"

    px_g = val["price_gordon"]
    shares = val["shares_outstanding"]
    assert abs((eq_g / shares) - px_g) < 1e-4, "Share price derivation mismatch"
    assert px_g > 0, "Implied target share price must be positive"


def test_sensitivity_matrix_properties() -> None:
    """Verify 2D sensitivity matrix dimensions and monotonic interest rate response."""
    hist = fetch_or_load_historical_financials()
    peers = fetch_or_load_peer_multiples()
    macro = fetch_or_load_macro_inputs()

    wacc_sched = build_wacc_schedule(macro, peers)
    forecast = build_five_year_forecast(hist)
    sens_matrix = generate_sensitivity_matrix(forecast, wacc_sched, macro, peers)

    assert sens_matrix.shape == (5, 7), "Sensitivity matrix must be 5 growth rows by 7 WACC columns"

    for i in range(sens_matrix.shape[0]):
        row_vals = sens_matrix.iloc[i].dropna().values
        diffs = np.diff(row_vals)
        assert np.all(diffs < 0), "Higher WACC must strictly reduce implied share price"


def test_comps_quartile_ordering() -> None:
    """Verify peer trading multiple percentiles satisfy strict ascending order."""
    peers = fetch_or_load_peer_multiples()
    stats = compute_peer_quartile_statistics(peers)

    for col in ["ev_to_revenue", "ev_to_ebitda", "trailing_pe"]:
        p25 = float(stats.loc["25th_percentile", col])
        med = float(stats.loc["median", col])
        p75 = float(stats.loc["75th_percentile", col])
        assert p25 <= med <= p75, f"Quartile ordering violated for multiple {col}"
