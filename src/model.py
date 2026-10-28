"""
Amazon (AMZN) valuation model: WACC, 5-year unlevered DCF, and credit metrics.

All reported figures come from data/amzn_fy2023_10k.json.
All judgment calls live in config/assumptions.json.
Nothing is hardcoded here, so every number in the output can be traced.
"""

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def load_inputs() -> tuple[dict, dict]:
    data = json.loads((ROOT / "data" / "amzn_fy2023_10k.json").read_text())
    assumptions = json.loads((ROOT / "config" / "assumptions.json").read_text())
    return data, assumptions


# ---------------------------------------------------------------------------
# Base year figures
# ---------------------------------------------------------------------------
def base_year(data: dict) -> dict:
    inc, cf, bs = data["income_statement"], data["cash_flow_statement"], data["balance_sheet"]
    net_capex = cf["operating_cash_flow"] - cf["free_cash_flow"]
    return {
        "revenue": inc["net_sales"],
        "ebit": inc["operating_income"],
        "ebitda": inc["operating_income"] + cf["depreciation_and_amortization"],
        "da": cf["depreciation_and_amortization"],
        "net_capex": net_capex,
        "effective_tax_rate": inc["provision_for_income_taxes"] / inc["income_before_income_taxes"],
        "debt": bs["long_term_debt_face_value_incl_current"],
        "cash": bs["cash_and_cash_equivalents"] + bs["marketable_securities"],
        "equity_book": bs["total_stockholders_equity"],
        "shares": data["shares"]["outstanding_at_year_end"],
    }


# ---------------------------------------------------------------------------
# WACC
# ---------------------------------------------------------------------------
def compute_wacc(data: dict, assumptions: dict) -> dict:
    m = assumptions["market"]
    base = base_year(data)

    cost_of_equity = m["risk_free_rate"] + m["beta"] * m["equity_risk_premium"]  # CAPM
    pre_tax_cost_of_debt = data["income_statement"]["interest_expense"] / base["debt"]
    after_tax_cost_of_debt = pre_tax_cost_of_debt * (1 - base["effective_tax_rate"])

    market_cap = m["share_price"] * base["shares"]
    total_capital = market_cap + base["debt"]
    w_e, w_d = market_cap / total_capital, base["debt"] / total_capital

    return {
        "cost_of_equity": cost_of_equity,
        "pre_tax_cost_of_debt": pre_tax_cost_of_debt,
        "after_tax_cost_of_debt": after_tax_cost_of_debt,
        "tax_rate": base["effective_tax_rate"],
        "market_cap": market_cap,
        "debt": base["debt"],
        "weight_equity": w_e,
        "weight_debt": w_d,
        "wacc": w_e * cost_of_equity + w_d * after_tax_cost_of_debt,
    }


# ---------------------------------------------------------------------------
# Free cash flow projection
# ---------------------------------------------------------------------------
def project_fcff(data: dict, assumptions: dict) -> pd.DataFrame:
    p = assumptions["projection"]
    base = base_year(data)
    tax = base["effective_tax_rate"] if p["tax_rate"] == "effective" else p["tax_rate"]

    rows, prev_rev = [], base["revenue"]
    for i, year in enumerate(p["years"]):
        rev = prev_rev * (1 + p["revenue_growth"][i])
        ebit = rev * p["ebit_margin"][i]
        nopat = ebit * (1 - tax)
        da = rev * p["da_pct_revenue"]
        capex = rev * p["capex_pct_revenue"][i]
        delta_nwc = (rev - prev_rev) * p["nwc_change_pct_incremental_revenue"]
        rows.append({
            "Year": f"{year}E",
            "Revenue": rev,
            "Growth": p["revenue_growth"][i],
            "EBIT": ebit,
            "EBIT margin": p["ebit_margin"][i],
            "NOPAT": nopat,
            "D&A": da,
            "Capex": capex,
            "Change in NWC": delta_nwc,
            "FCFF": nopat + da - capex - delta_nwc,
        })
        prev_rev = rev
    return pd.DataFrame(rows).set_index("Year")


# ---------------------------------------------------------------------------
# DCF
# ---------------------------------------------------------------------------
def dcf_value(proj: pd.DataFrame, wacc: float, g: float, base: dict) -> dict:
    if wacc <= g:
        raise ValueError("WACC must be greater than terminal growth")

    periods = range(1, len(proj) + 1)
    discount = [(1 + wacc) ** t for t in periods]
    pv_fcff = sum(f / d for f, d in zip(proj["FCFF"], discount))

    terminal_value = proj["FCFF"].iloc[-1] * (1 + g) / (wacc - g)  # Gordon growth
    pv_terminal = terminal_value / discount[-1]

    enterprise_value = pv_fcff + pv_terminal
    equity_value = enterprise_value - base["debt"] + base["cash"]
    return {
        "pv_fcff": pv_fcff,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "terminal_share_of_ev": pv_terminal / enterprise_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "value_per_share": equity_value / base["shares"],
    }


def sensitivity(proj: pd.DataFrame, base: dict, wacc_range: list, g_range: list) -> pd.DataFrame:
    table = pd.DataFrame(index=[f"{w:.1%}" for w in wacc_range], columns=[f"{g:.1%}" for g in g_range], dtype=float)
    for w in wacc_range:
        for g in g_range:
            table.loc[f"{w:.1%}", f"{g:.1%}"] = dcf_value(proj, w, g, base)["value_per_share"]
    table.index.name = "WACC \\ Terminal growth"
    return table


# ---------------------------------------------------------------------------
# Credit metrics (lender's view)
# ---------------------------------------------------------------------------
def credit_metrics(data: dict) -> dict:
    base = base_year(data)
    interest = data["income_statement"]["interest_expense"]
    debt_service = data["debt_maturities"]["principal_and_interest_due_2024"]
    net_debt = base["debt"] - base["cash"]
    return {
        "EBITDA": base["ebitda"],
        "Total debt / EBITDA": base["debt"] / base["ebitda"],
        "Net debt / EBITDA": net_debt / base["ebitda"],
        "EBIT / interest (interest coverage)": base["ebit"] / interest,
        "EBITDA / interest": base["ebitda"] / interest,
        "DSCR (EBITDA / next-year principal + interest)": base["ebitda"] / debt_service,
        "Debt / equity (book)": base["debt"] / base["equity_book"],
        "Debt / total capital (book)": base["debt"] / (base["debt"] + base["equity_book"]),
    }


# ---------------------------------------------------------------------------
# Reverse DCF: what does the market price assume?
# ---------------------------------------------------------------------------
def _solve(func, target: float, lo: float, hi: float, iterations: int = 80) -> float:
    """Simple bisection. func must increase as its input increases."""
    for _ in range(iterations):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if func(mid) < target else (lo, mid)
    return (lo + hi) / 2


def implied_terminal_growth(data: dict, assumptions: dict, wacc: float, target_price: float) -> float:
    base, proj = base_year(data), project_fcff(data, assumptions)
    return _solve(lambda g: dcf_value(proj, wacc, g, base)["value_per_share"], target_price, 0.0, wacc - 1e-4)


def implied_final_year_margin(data: dict, assumptions: dict, wacc: float, target_price: float) -> float:
    base = base_year(data)
    g = assumptions["projection"]["terminal_growth"]

    def price_at(margin: float) -> float:
        tweaked = json.loads(json.dumps(assumptions))
        tweaked["projection"]["ebit_margin"][-1] = margin
        return dcf_value(project_fcff(data, tweaked), wacc, g, base)["value_per_share"]

    return _solve(price_at, target_price, 0.0, 0.6)
