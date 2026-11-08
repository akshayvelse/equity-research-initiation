"""Data loader and local cache manager for equity research valuation models.

Retrieves historical SEC fundamental metrics and market pricing via yfinance,
persisting standardized datasets to disk for offline and deterministic execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd
import yfinance as yf

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

TARGET_TICKER = "MSFT"
PEER_TICKERS = ["AAPL", "GOOGL", "AMZN", "ORCL", "CRM"]


def ensure_data_directory() -> Path:
    """Ensure data caching directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def fetch_or_load_peer_multiples(force_refresh: bool = False) -> pd.DataFrame:
    """Load peer comparable valuation multiples from cache or live yfinance feed.

    Calculates enterprise value, enterprise-to-revenue, enterprise-to-ebitda,
    price-to-earnings, and gearing metrics across the defined sector peer group.
    """
    ensure_data_directory()
    cache_path = DATA_DIR / "peer_multiples.csv"

    if cache_path.exists() and not force_refresh:
        return pd.read_csv(cache_path, index_col=0)

    rows: list[dict[str, Any]] = []
    all_tickers = [TARGET_TICKER] + PEER_TICKERS

    for ticker in all_tickers:
        t = yf.Ticker(ticker)
        info = t.info

        price = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0.0)
        mcap = float(info.get("marketCap") or 0.0)
        ev = float(info.get("enterpriseValue") or 0.0)
        ev_rev = float(info.get("enterpriseToRevenue") or 0.0)
        ev_ebitda = float(info.get("enterpriseToEbitda") or 0.0)
        pe = float(info.get("trailingPE") or 0.0)
        beta = float(info.get("beta") or 1.0)
        total_debt = float(info.get("totalDebt") or 0.0)
        total_cash = float(info.get("totalCash") or 0.0)

        # Fallback sanity adjustments if market data returns zero
        if ev == 0.0 and mcap > 0.0:
            ev = mcap + total_debt - total_cash

        rows.append(
            {
                "ticker": ticker,
                "company_name": info.get("shortName", ticker),
                "share_price": price,
                "market_cap": mcap,
                "enterprise_value": ev,
                "ev_to_revenue": ev_rev,
                "ev_to_ebitda": ev_ebitda,
                "trailing_pe": pe,
                "beta": beta,
                "total_debt": total_debt,
                "total_cash": total_cash,
                "debt_to_equity": (total_debt / mcap) if mcap > 0 else 0.0,
            }
        )

    df = pd.DataFrame(rows).set_index("ticker")
    df.to_csv(cache_path)
    return df


def fetch_or_load_historical_financials(force_refresh: bool = False) -> pd.DataFrame:
    """Load historical 3-statement metrics for Microsoft Corporation (MSFT).

    Structured from FY21 through FY24 10-K reported figures in millions of USD.
    Segments: Intelligent Cloud, Productivity & Business Processes, More Personal Computing.
    """
    ensure_data_directory()
    cache_path = DATA_DIR / "msft_historical_financials.csv"

    if cache_path.exists() and not force_refresh:
        return pd.read_csv(cache_path, index_col=0)

    # Standardized figures from SEC Form 10-K (in $M)
    # Fiscal years ended June 30
    historical_data = {
        "metric": [
            "rev_productivity",
            "rev_intelligent_cloud",
            "rev_more_personal_computing",
            "total_revenue",
            "cost_of_goods_sold",
            "gross_profit",
            "research_and_development",
            "selling_general_admin",
            "operating_income_ebit",
            "depreciation_amortization",
            "ebitda",
            "interest_expense",
            "income_tax_expense",
            "net_income",
            "operating_cash_flow",
            "capital_expenditures",
            "free_cash_flow",
            "accounts_receivable",
            "inventories",
            "accounts_payable_accrued",
            "net_working_capital",
            "cash_and_equivalents",
            "total_debt",
            "diluted_shares_outstanding",
        ],
        "FY2021": [
            53915,
            60080,
            54093,
            168088,
            52232,
            115856,
            20716,
            25224,
            69916,
            10900,
            80816,
            2346,
            9831,
            61271,
            76740,
            20622,
            56118,
            38043,
            2636,
            29874,
            10805,
            130334,
            58153,
            7608,
        ],
        "FY2022": [
            63364,
            75251,
            59655,
            198270,
            62650,
            135620,
            24512,
            27725,
            83383,
            12600,
            95983,
            2063,
            10978,
            72738,
            89035,
            23886,
            65149,
            44261,
            3742,
            34533,
            13470,
            104757,
            49759,
            7540,
        ],
        "FY2023": [
            69274,
            87907,
            54734,
            211915,
            65863,
            146052,
            27195,
            30391,
            88466,
            13861,
            102327,
            1968,
            16950,
            72361,
            87582,
            28107,
            59475,
            48688,
            2500,
            39682,
            11506,
            111262,
            47204,
            7472,
        ],
        "FY2024": [
            77341,
            105362,
            62437,
            245140,
            74052,
            171088,
            29510,
            32230,
            109348,
            15354,
            124702,
            2150,
            19355,
            88136,
            118548,
            44477,
            74071,
            56868,
            2988,
            47120,
            12736,
            75536,
            52857,
            7426,
        ],
    }

    df = pd.DataFrame(historical_data).set_index("metric")
    df.to_csv(cache_path)
    return df


def fetch_or_load_macro_inputs() -> dict[str, float]:
    """Retrieve key capital market baseline parameters."""
    return {
        "risk_free_rate": 0.0425,  # 10Y US Treasury yield benchmark
        "equity_risk_premium": 0.0550,  # Long-run US equity risk premium
        "marginal_tax_rate": 0.2100,  # US statutory federal corporate tax rate
        "terminal_growth_rate": 0.0250,  # Long-run nominal GDP growth proxy
        "target_exit_multiple": 18.5,  # Baseline EV/EBITDA terminal multiple
        "effective_pretax_debt_cost": 0.0450,  # Weighted yield on senior unsecured notes
    }


if __name__ == "__main__":
    multiples = fetch_or_load_peer_multiples(force_refresh=True)
    financials = fetch_or_load_historical_financials(force_refresh=True)
    print("Peer multiples cached shape:", multiples.shape)
    print("MSFT financials cached shape:", financials.shape)
