"""Unit tests for deterministic financial calculation tools."""
import pytest
from tools.calculation_tools import (
    calculate_unit_economics,
    calculate_margins,
    calculate_break_even,
    calculate_runway,
    run_downside_stress_test,
)


def test_unit_economics():
    # CAC = $100, ARPU = $50/mo, Gross margin = 80%, Churn = 5%/mo
    # Monthly profit per customer = 50 * 0.8 = $40
    # LTV = 40 / 0.05 = $800
    # LTV:CAC = 800 / 100 = 8.0 (healthy)
    res = calculate_unit_economics(
        cac=100.0,
        arpu_monthly=50.0,
        gross_margin_percent=80.0,
        churn_rate_monthly=0.05,
    )
    assert res.ltv == 800.0
    assert res.ltv_to_cac_ratio == 8.0
    assert res.is_healthy is True
    assert res.payback_months == 2.5


def test_margins():
    # Revenue = 100,000, COGS = 30,000, Variable OpEx = 10,000
    # Gross Profit = 70,000 (70%)
    # Contribution Margin = 60,000 (60%)
    res = calculate_margins(revenue=100000.0, cogs=30000.0, variable_operating_expenses=10000.0)
    assert res.gross_profit == 70000.0
    assert res.gross_margin_percent == 70.0
    assert res.contribution_margin_percent == 60.0


def test_break_even():
    # Fixed costs = $50,000, Price = $100, Variable cost = $20
    # CM per unit = $80
    # Break-even units = 50,000 / 80 = 625 units
    # Break-even revenue = 625 * 100 = $62,500
    res = calculate_break_even(fixed_costs=50000.0, unit_price=100.0, variable_cost_per_unit=20.0)
    assert res.contribution_margin_per_unit == 80.0
    assert res.break_even_units == 625.0
    assert res.break_even_revenue == 62500.0


def test_runway():
    # Cash = $300,000, Monthly expenses = $60,000, Monthly revenue = $10,000
    # Net burn = $50,000
    # Runway = 300,000 / 50,000 = 6.0 months (not critical yet)
    res = calculate_runway(cash_balance=300000.0, monthly_expenses=60000.0, monthly_revenue=10000.0)
    assert res.net_monthly_burn == 50000.0
    assert res.runway_months == 6.0
    assert res.is_critical is False

    # Low cash -> critical
    res_crit = calculate_runway(cash_balance=100000.0, monthly_expenses=50000.0, monthly_revenue=0.0)
    assert res_crit.runway_months == 2.0
    assert res_crit.is_critical is True


def test_downside_stress_test():
    # Base revenue = $100k, Base costs = $70k -> Base profit = $30k
    # 20% revenue drop -> $80k
    # 15% cost increase -> $80.5k
    # Stressed profit = 80 - 80.5 = -0.5k (fails downside test)
    res = run_downside_stress_test(
        base_revenue=100000.0,
        base_costs=70000.0,
        revenue_drop_percent=20.0,
        cost_increase_percent=15.0,
    )
    assert res["base_profit"] == 30000.0
    assert res["stressed_revenue"] == 80000.0
    assert res["stressed_costs"] == 80500.0
    assert res["stressed_profit"] == -500.0
    assert res["survives_downside"] is False
