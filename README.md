# Equity Research Initiation: Microsoft Corporation (NASDAQ:MSFT)

An institutional valuation model and equity research initiation framework covering Microsoft Corporation (NASDAQ:MSFT) alongside 5 large-cap technology peers (AAPL, GOOGL, AMZN, ORCL, CRM).

## Directory Architecture

```
01_equity_research_initiation/
├── README.md
├── investment_memo.md
├── data/
│   ├── msft_historical_financials.csv
│   └── peer_multiples.csv
├── src/
│   ├── __init__.py
│   ├── data_loader.py
│   ├── dcf_engine.py
│   ├── comps_engine.py
│   └── excel_generator.py
└── output/
    ├── dcf_comps_valuation_model.xlsx
    └── sensitivity_surface.png
```

## Methodology & Structural Modeling

### 1. 3-Statement Operating Forecast & Mid-Year DCF (`src/dcf_engine.py`)
- **Explicit 5-Year Horizon (FY25E-FY29E):** Segment-level top-line growth across Intelligent Cloud, Productivity & Business Processes, and More Personal Computing.
- **Operating Margin & Fixed-Cost Absorption:** Cost of Goods Sold (COGS), R&D, and SG&A modeled as dynamic revenue percentages reflecting infrastructure scaling.
- **Balance Sheet Working Capital Schedules:** Models Accounts Receivable (DSO 56 days), Inventories (DIO 15 days), and Accounts Payable (DPO 48 days).
- **Free Cash Flow to Firm (FCFF):**
  $$\text{NOPAT} = \text{EBIT} \times (1 - t)$$
  $$\text{FCFF} = \text{NOPAT} + \text{D&A} - \text{CapEx} - \Delta\text{NWC}$$
- **Mid-Year Discounting Convention:** Applies discount factors $\text{DF}_t = (1 + \text{WACC})^{-(t - 0.5)}$ for $t \in [1, 5]$.
- **Terminal Value Formulations:**
  - Gordon Growth (Perpetuity): $\text{TV} = \frac{\text{FCFF}_5 \times (1 + g)}{\text{WACC} - g}$ discounted by $(1 + \text{WACC})^{-5}$.
  - Exit Multiple: $\text{TV} = \text{EBITDA}_5 \times \text{Multiple}$ discounted by $(1 + \text{WACC})^{-5}$.
- **Bottom-Up WACC:** Un-gears peer betas via the Hamada equation, computes median asset beta (1.15), re-gears to target capital structure, and yields 9.50% WACC based on a 4.25% 10-year Treasury yield and 5.50% equity risk premium.

### 2. Comparable Company Trading Analysis (`src/comps_engine.py`)
- Pulls live peer fundamental metrics via yfinance and calculates non-parametric distributions (25th percentile, median, mean, 75th percentile) across:
  - Enterprise Value / Revenue
  - Enterprise Value / EBITDA
  - Trailing Price / Earnings
- Bridges implied enterprise values to equity values and share prices using target net debt and diluted share counts.

### 3. Investment Banking Excel Model (`src/excel_generator.py`)
- Builds `output/dcf_comps_valuation_model.xlsx` using `openpyxl`.
- Implements Wall Street financial modeling typography:
  - Blue font (`#0000FF`): Hardcoded historical inputs and assumptions.
  - Black font (`#000000`): Same-sheet calculation formulas.
  - Green font (`#006100`): Dynamic cross-sheet workbook links.
  - Top thin / bottom double accounting underlines on all balance sheets and totals.

## Execution

```bash
# Fetch and cache fundamental datasets
python 01_equity_research_initiation/src/data_loader.py

# Run DCF valuation and generate 2D sensitivity heatmap
python 01_equity_research_initiation/src/dcf_engine.py

# Compute peer multiple distributions and implied valuations
python 01_equity_research_initiation/src/comps_engine.py

# Generate live multi-tab Excel workbook
python 01_equity_research_initiation/src/excel_generator.py
```
