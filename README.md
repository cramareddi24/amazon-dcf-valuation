# Amazon (AMZN) DCF Valuation and Credit Analysis

A Python valuation model for Amazon built from its FY2023 10-K: WACC, a 5-year unlevered DCF, a sensitivity table, a reverse DCF, and lender-style credit metrics.

This started as a corporate finance project at San José State, where I analyzed Amazon's cost of capital, valuation, and credit profile. I rebuilt it in Python so every input is traceable and every assumption can be changed and re-run in seconds instead of rebuilding spreadsheet links.

## Structure of the model

1. **Inputs, split on purpose**
   - [`data/amzn_fy2023_10k.json`](data/amzn_fy2023_10k.json): reported figures only, straight from the 10-K
   - [`config/assumptions.json`](config/assumptions.json): every judgment call (growth, margins, beta, risk-free rate, terminal growth)
2. **WACC**: CAPM cost of equity, cost of debt from interest expense over debt, market-value weights
3. **FCFF projection**: revenue, EBIT, NOPAT, D&A, capex, and working capital for 2024E to 2028E
4. **DCF**: discounted cash flows plus a Gordon growth terminal value, bridged from enterprise value to value per share
5. **Sensitivity**: value per share across a grid of WACC and terminal growth rates
6. **Reverse DCF**: solves for the margin or growth rate the market price implies
7. **Credit metrics**: leverage, interest coverage, and DSCR from a lender's point of view

## Results

| | |
|---|---|
| WACC | 9.91% |
| Enterprise value | $1,035.8B |
| Equity value | $1,055.4B |
| **Value per share** | **$101.65** |
| Market price (fall 2024, assumed) | ~$185 |
| Terminal value share of EV | 78.5% |

**What I took from it:** under these assumptions the model lands well below the market price. Instead of stopping there, I ran a reverse DCF to see what the market is assuming. To justify ~$185, Amazon would need roughly a **24% EBIT margin by 2028** (vs 12.5% assumed) or **6.5% perpetual growth**, which no company sustains forever. So the market is betting on a longer high-growth runway and a bigger shift toward high-margin businesses like AWS and advertising than a 5-year model can capture. The useful output isn't "buy or sell," it's knowing exactly which assumptions the price depends on.

![Sensitivity heatmap](outputs/charts/sensitivity_heatmap.png)

### Credit profile (FY2023)

| Metric | Value |
|---|---|
| Total debt / EBITDA | 0.79x |
| Net debt / EBITDA | -0.23x (more cash than debt) |
| EBIT / interest | 11.58x |
| DSCR (EBITDA / 2024 principal + interest) | 8.06x |
| Debt / total capital (book) | 0.25 |

From a lender's view, Amazon is a very low-risk borrower: net cash position, double-digit interest coverage, and 8x coverage of next year's scheduled debt service. One caveat I call out in the report: lease liabilities ($77.3B long-term) are excluded from debt here, and including them would raise leverage meaningfully.

Full output: [outputs/valuation_summary.md](outputs/valuation_summary.md)

## How to run

```bash
pip install -r requirements.txt
python run_model.py
```

To test a different view, edit `config/assumptions.json` (for example, raise the 2028 EBIT margin or lower beta) and run it again.

## Project structure

```
amazon-dcf-valuation/
├── data/amzn_fy2023_10k.json     # reported figures from the 10-K
├── config/assumptions.json       # all assumptions in one place
├── src/model.py                  # WACC, projections, DCF, sensitivity, reverse DCF, credit metrics
├── run_model.py                  # runs everything and writes outputs/
└── outputs/
    ├── valuation_summary.md
    ├── projections.csv
    ├── sensitivity.csv
    └── charts/
```

## Data sources and simplifications

- Financials: Amazon Form 10-K for fiscal year 2023 (SEC EDGAR). Free cash flow follows Amazon's own definition, so net capex is derived as operating cash flow minus free cash flow.
- Market inputs (share price, risk-free rate, beta, equity risk premium) are approximate fall 2024 values and are labeled as assumptions.
- Debt uses the face value of long-term debt including the current portion. Leases are excluded.
- Single effective tax rate (FY2023) applied to all projection years.

This is an educational model, not investment advice.

## Tools

Python, pandas, matplotlib
