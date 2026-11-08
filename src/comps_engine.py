"""Comparable company analysis (Trading Comps) valuation engine.

Evaluates peer trading multiples across enterprise value and equity value metrics,
computes non-parametric quartile distributions (25th percentile, median, mean, 75th percentile),
and derives implied target share price ranges for Microsoft Corporation (MSFT).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

try:
    from .data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_peer_multiples,
    )
except ImportError:
    sys.path.append(str(Path(__file__).resolve().parent))
    from data_loader import (
        fetch_or_load_historical_financials,
        fetch_or_load_peer_multiples,
    )


def compute_peer_quartile_statistics(
    peer_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Calculate statistical distribution of peer trading valuation multiples.

    Excludes target company to avoid circular self-referencing.
    Computes 25th percentile, median, mean, and 75th percentile for:
    - EV / Revenue
    - EV / EBITDA
    - Trailing P / E
    """
    if peer_df is None:
        peer_df = fetch_or_load_peer_multiples()

    peers_only = peer_df.loc[peer_df.index != "MSFT"]

    metrics = ["ev_to_revenue", "ev_to_ebitda", "trailing_pe"]
    clean_peers = peers_only[metrics].copy()

    stats_dict: dict[str, dict[str, float]] = {}
    for col in metrics:
        s = clean_peers[col].dropna()
        stats_dict[col] = {
            "25th_percentile": float(np.percentile(s, 25)),
            "median": float(np.median(s)),
            "mean": float(np.mean(s)),
            "75th_percentile": float(np.percentile(s, 75)),
        }

    return pd.DataFrame(stats_dict)


def derive_implied_valuation_ranges(
    peer_stats: pd.DataFrame,
    target_ticker: str = "MSFT",
    peer_df: pd.DataFrame | None = None,
    financials_df: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Derive implied equity value and share price ranges from peer multiple distributions.

    Bridge formulas:
        From EV/EBITDA: Implied EV = Multiple * Target_EBITDA
                        Implied Equity = Implied EV + Cash - Debt
                        Implied Price = Implied Equity / Diluted Shares
        From P/E:       Implied Equity = Multiple * Target_Net_Income
                        Implied Price = Implied Equity / Diluted Shares
        From EV/Rev:    Implied EV = Multiple * Target_Revenue
                        Implied Equity = Implied EV + Cash - Debt
                        Implied Price = Implied Equity / Diluted Shares
    """
    if peer_df is None:
        peer_df = fetch_or_load_peer_multiples()
    if financials_df is None:
        financials_df = fetch_or_load_historical_financials()

    target_row = peer_df.loc[target_ticker]
    cash_val = float(target_row["total_cash"]) / 1e6  # in $M
    debt_val = float(target_row["total_debt"]) / 1e6  # in $M
    shares_out = (float(target_row["market_cap"]) / float(target_row["share_price"])) / 1e6  # in M shares

    # FY24 baseline fundamentals in $M
    ltm_rev = float(financials_df.loc["total_revenue", "FY2024"])
    ltm_ebitda = float(financials_df.loc["ebitda", "FY2024"])
    ltm_net_income = float(financials_df.loc["net_income", "FY2024"])

    quartiles = ["25th_percentile", "median", "mean", "75th_percentile"]

    summary_rows: list[dict[str, Any]] = []

    # EV / EBITDA Implied Valuation
    for q in quartiles:
        mult = float(peer_stats.loc[q, "ev_to_ebitda"])
        implied_ev = mult * ltm_ebitda
        implied_equity = implied_ev + cash_val - debt_val
        implied_share_price = implied_equity / shares_out
        summary_rows.append(
            {
                "method": "EV / EBITDA",
                "statistic": q,
                "multiple": mult,
                "target_metric_m": ltm_ebitda,
                "implied_ev_m": implied_ev,
                "implied_equity_m": implied_equity,
                "implied_share_price": implied_share_price,
            }
        )

    # Trailing P / E Implied Valuation
    for q in quartiles:
        mult = float(peer_stats.loc[q, "trailing_pe"])
        implied_equity = mult * ltm_net_income
        implied_ev = implied_equity - cash_val + debt_val
        implied_share_price = implied_equity / shares_out
        summary_rows.append(
            {
                "method": "P / E",
                "statistic": q,
                "multiple": mult,
                "target_metric_m": ltm_net_income,
                "implied_ev_m": implied_ev,
                "implied_equity_m": implied_equity,
                "implied_share_price": implied_share_price,
            }
        )

    # EV / Revenue Implied Valuation
    for q in quartiles:
        mult = float(peer_stats.loc[q, "ev_to_revenue"])
        implied_ev = mult * ltm_rev
        implied_equity = implied_ev + cash_val - debt_val
        implied_share_price = implied_equity / shares_out
        summary_rows.append(
            {
                "method": "EV / Revenue",
                "statistic": q,
                "multiple": mult,
                "target_metric_m": ltm_rev,
                "implied_ev_m": implied_ev,
                "implied_equity_m": implied_equity,
                "implied_share_price": implied_share_price,
            }
        )

    result_df = pd.DataFrame(summary_rows)

    return {
        "peer_multiples_table": peer_df,
        "peer_statistics": peer_stats,
        "implied_valuation_table": result_df,
        "current_market_price": float(target_row["share_price"]),
        "target_ebitda": ltm_ebitda,
        "target_net_income": ltm_net_income,
        "target_revenue": ltm_rev,
    }


if __name__ == "__main__":
    p_df = fetch_or_load_peer_multiples()
    stats = compute_peer_quartile_statistics(p_df)
    results = derive_implied_valuation_ranges(stats, peer_df=p_df)

    print("=== PEER MULTIPLE QUARTILES ===")
    print(stats.to_string())
    print("\n=== IMPLIED VALUATION SUMMARY ===")
    print(results["implied_valuation_table"][["method", "statistic", "multiple", "implied_share_price"]].to_string())
