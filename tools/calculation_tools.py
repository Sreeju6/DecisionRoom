"""Deterministic financial calculation tools for DecisionRoom.

Provides exact, verifiable arithmetic for:
- Unit economics (CAC, LTV, LTV:CAC ratio)
- Gross margin and contribution margin percentages
- Break-even revenue and sales volume
- Runway and monthly burn rate
- Downside stress scenario modeling

Never relies on LLM arithmetic.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class UnitEconomicsResult(BaseModel):
    cac: float = Field(..., ge=0.0)
    ltv: float = Field(..., ge=0.0)
    ltv_to_cac_ratio: float = Field(..., ge=0.0)
    payback_months: Optional[float] = None
    is_healthy: bool = Field(..., description="Healthy if LTV:CAC >= 3.0")


class MarginResult(BaseModel):
    revenue: float = Field(..., ge=0.0)
    cogs: float = Field(..., ge=0.0)
    gross_profit: float
    gross_margin_percent: float
    contribution_margin_percent: Optional[float] = None


class BreakEvenResult(BaseModel):
    fixed_costs: float = Field(..., ge=0.0)
    unit_price: float = Field(..., gt=0.0)
    variable_cost_per_unit: float = Field(..., ge=0.0)
    contribution_margin_per_unit: float
    break_even_units: float
    break_even_revenue: float


class RunwayResult(BaseModel):
    cash_balance: float = Field(..., ge=0.0)
    monthly_expenses: float = Field(..., ge=0.0)
    monthly_revenue: float = Field(default=0.0, ge=0.0)
    net_monthly_burn: float
    runway_months: float
    is_critical: bool = Field(..., description="Critical if runway < 6 months")


def calculate_unit_economics(
    cac: float,
    arpu_monthly: float,
    gross_margin_percent: float,
    churn_rate_monthly: float,
) -> UnitEconomicsResult:
    """Calculate exact LTV and LTV:CAC ratio.
    
    LTV = (ARPU * Gross Margin) / Churn Rate
    """
    if cac < 0:
        raise ValueError("CAC cannot be negative.")
    if churn_rate_monthly <= 0:
        raise ValueError("Churn rate must be greater than zero.")
    if arpu_monthly < 0:
        raise ValueError("ARPU cannot be negative.")

    margin_decimal = gross_margin_percent / 100.0 if gross_margin_percent > 1.0 else gross_margin_percent
    monthly_profit_per_customer = arpu_monthly * margin_decimal
    ltv = monthly_profit_per_customer / churn_rate_monthly

    ratio = round(ltv / cac, 2) if cac > 0 else float("inf")
    payback = round(cac / monthly_profit_per_customer, 1) if monthly_profit_per_customer > 0 else None

    return UnitEconomicsResult(
        cac=round(cac, 2),
        ltv=round(ltv, 2),
        ltv_to_cac_ratio=ratio,
        payback_months=payback,
        is_healthy=ratio >= 3.0,
    )


def calculate_margins(
    revenue: float,
    cogs: float,
    variable_operating_expenses: float = 0.0,
) -> MarginResult:
    """Calculate gross profit and margin percentages."""
    if revenue < 0 or cogs < 0:
        raise ValueError("Revenue and COGS cannot be negative.")
    if revenue == 0:
        return MarginResult(
            revenue=0.0,
            cogs=cogs,
            gross_profit=-cogs,
            gross_margin_percent=0.0,
            contribution_margin_percent=0.0,
        )

    gross_profit = revenue - cogs
    gross_margin = (gross_profit / revenue) * 100.0

    contribution_profit = gross_profit - variable_operating_expenses
    contribution_margin = (contribution_profit / revenue) * 100.0

    return MarginResult(
        revenue=round(revenue, 2),
        cogs=round(cogs, 2),
        gross_profit=round(gross_profit, 2),
        gross_margin_percent=round(gross_margin, 2),
        contribution_margin_percent=round(contribution_margin, 2),
    )


def calculate_break_even(
    fixed_costs: float,
    unit_price: float,
    variable_cost_per_unit: float,
) -> BreakEvenResult:
    """Calculate break-even units and break-even revenue."""
    if fixed_costs < 0 or unit_price <= 0 or variable_cost_per_unit < 0:
        raise ValueError("Invalid cost or pricing parameters.")
    if variable_cost_per_unit >= unit_price:
        raise ValueError("Variable cost per unit must be strictly less than unit price.")

    cm_per_unit = unit_price - variable_cost_per_unit
    be_units = math.ceil(fixed_costs / cm_per_unit)
    be_revenue = round(be_units * unit_price, 2)

    return BreakEvenResult(
        fixed_costs=round(fixed_costs, 2),
        unit_price=round(unit_price, 2),
        variable_cost_per_unit=round(variable_cost_per_unit, 2),
        contribution_margin_per_unit=round(cm_per_unit, 2),
        break_even_units=float(be_units),
        break_even_revenue=be_revenue,
    )


def calculate_runway(
    cash_balance: float,
    monthly_expenses: float,
    monthly_revenue: float = 0.0,
) -> RunwayResult:
    """Calculate net monthly burn and cash runway in months."""
    if cash_balance < 0 or monthly_expenses < 0 or monthly_revenue < 0:
        raise ValueError("Financial balance and cash flow amounts cannot be negative.")

    net_burn = monthly_expenses - monthly_revenue
    if net_burn <= 0:
        runway = float("inf")
    else:
        runway = round(cash_balance / net_burn, 1)

    return RunwayResult(
        cash_balance=round(cash_balance, 2),
        monthly_expenses=round(monthly_expenses, 2),
        monthly_revenue=round(monthly_revenue, 2),
        net_monthly_burn=round(net_burn, 2),
        runway_months=runway,
        is_critical=runway < 6.0,
    )


def run_downside_stress_test(
    base_revenue: float,
    base_costs: float,
    revenue_drop_percent: float = 20.0,
    cost_increase_percent: float = 15.0,
) -> Dict[str, Any]:
    """Model downside stress test scenario."""
    stressed_rev = base_revenue * (1.0 - (revenue_drop_percent / 100.0))
    stressed_costs = base_costs * (1.0 + (cost_increase_percent / 100.0))
    net_profit_base = base_revenue - base_costs
    net_profit_stressed = stressed_rev - stressed_costs

    return {
        "base_profit": round(net_profit_base, 2),
        "stressed_revenue": round(stressed_rev, 2),
        "stressed_costs": round(stressed_costs, 2),
        "stressed_profit": round(net_profit_stressed, 2),
        "profit_delta": round(net_profit_stressed - net_profit_base, 2),
        "survives_downside": net_profit_stressed >= 0,
    }
