import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


Number = float


def _sum_overheads(overheads: Dict[str, Number]) -> Number:
    return sum(overheads.values())


def _safe_get(item: Dict[str, Any], key: str, default: Number = 0.0) -> Number:
    value = item.get(key, default)
    return float(value)


@dataclass
class PnL:
    revenue: Number
    variable_costs: Number
    fixed_costs: Number
    contribution_margin: Number
    profit_before_tax: Number
    break_even_units: Optional[Number] = None
    break_even_fill_rate: Optional[Number] = None


def compute_jewelry(config: Dict[str, Any]) -> Dict[str, Any]:
    channels: List[Dict[str, Any]] = config.get("channels", [])
    overheads: Dict[str, Number] = config.get("overheads", {})
    fixed_costs = _sum_overheads(overheads)

    channel_results = []
    total_revenue = 0.0
    total_variable_costs = 0.0

    for channel in channels:
        units = _safe_get(channel, "units", 0)
        price = _safe_get(channel, "avg_price", 0)
        unit_cost = _safe_get(channel, "unit_cost", 0)
        discount_rate = _safe_get(channel, "discount_rate", 0)
        return_rate = _safe_get(channel, "return_rate", 0)
        payment_fee_rate = _safe_get(channel, "payment_fee_rate", 0)
        channel_fee_rate = _safe_get(channel, "channel_fee_rate", 0)
        variable_ops_cost = _safe_get(channel, "variable_ops_cost", 0)

        effective_price = price * (1 - discount_rate)
        sold_units = units * (1 - return_rate)
        net_revenue = sold_units * effective_price
        variable_costs = sold_units * (unit_cost + variable_ops_cost)
        payment_fees = net_revenue * payment_fee_rate
        channel_fees = net_revenue * channel_fee_rate
        variable_total = variable_costs + payment_fees + channel_fees
        contribution = net_revenue - variable_total

        margin_per_unit = 0.0
        if sold_units:
            margin_per_unit = contribution / sold_units
        break_even_units = None
        if margin_per_unit > 0:
            break_even_units = fixed_costs / margin_per_unit

        channel_results.append(
            {
                "name": channel.get("name", "channel"),
                "gross_revenue": units * price,
                "net_revenue": net_revenue,
                "sold_units": sold_units,
                "variable_costs": variable_total,
                "contribution": contribution,
                "margin_per_unit": margin_per_unit,
                "break_even_units": break_even_units,
            }
        )

        total_revenue += net_revenue
        total_variable_costs += variable_total

    contribution_margin = total_revenue - total_variable_costs
    profit_before_tax = contribution_margin - fixed_costs

    return {
        "pnl": PnL(
            revenue=total_revenue,
            variable_costs=total_variable_costs,
            fixed_costs=fixed_costs,
            contribution_margin=contribution_margin,
            profit_before_tax=profit_before_tax,
            break_even_units=channel_results[0]["break_even_units"] if channel_results else None,
        ).__dict__,
        "channels": channel_results,
        "fixed_costs_detail": overheads,
    }


def compute_retail(config: Dict[str, Any]) -> Dict[str, Any]:
    categories: List[Dict[str, Any]] = config.get("categories", [])
    overheads: Dict[str, Number] = config.get("overheads", {})
    fixed_costs = _sum_overheads(overheads)

    cat_results = []
    total_revenue = 0.0
    total_variable_costs = 0.0

    for category in categories:
        units = _safe_get(category, "units", 0)
        price = _safe_get(category, "avg_price", 0)
        unit_cost = _safe_get(category, "unit_cost", 0)
        discount_rate = _safe_get(category, "discount_rate", 0)
        return_rate = _safe_get(category, "return_rate", 0)
        payment_fee_rate = _safe_get(category, "payment_fee_rate", 0)
        channel_fee_rate = _safe_get(category, "channel_fee_rate", 0)
        variable_ops_cost = _safe_get(category, "variable_ops_cost", 0)

        effective_price = price * (1 - discount_rate)
        sold_units = units * (1 - return_rate)
        net_revenue = sold_units * effective_price
        variable_costs = sold_units * (unit_cost + variable_ops_cost)
        payment_fees = net_revenue * payment_fee_rate
        channel_fees = net_revenue * channel_fee_rate
        variable_total = variable_costs + payment_fees + channel_fees
        contribution = net_revenue - variable_total

        margin_per_unit = 0.0
        if sold_units:
            margin_per_unit = contribution / sold_units
        break_even_units = None
        if margin_per_unit > 0:
            break_even_units = fixed_costs / margin_per_unit

        cat_results.append(
            {
                "name": category.get("name", "category"),
                "gross_revenue": units * price,
                "net_revenue": net_revenue,
                "sold_units": sold_units,
                "variable_costs": variable_total,
                "contribution": contribution,
                "margin_per_unit": margin_per_unit,
                "break_even_units": break_even_units,
            }
        )

        total_revenue += net_revenue
        total_variable_costs += variable_total

    contribution_margin = total_revenue - total_variable_costs
    profit_before_tax = contribution_margin - fixed_costs

    return {
        "pnl": PnL(
            revenue=total_revenue,
            variable_costs=total_variable_costs,
            fixed_costs=fixed_costs,
            contribution_margin=contribution_margin,
            profit_before_tax=profit_before_tax,
            break_even_units=cat_results[0]["break_even_units"] if cat_results else None,
        ).__dict__,
        "categories": cat_results,
        "fixed_costs_detail": overheads,
    }


def compute_yoga(config: Dict[str, Any]) -> Dict[str, Any]:
    overheads: Dict[str, Number] = config.get("overheads", {})
    fixed_costs = _sum_overheads(overheads)

    classes = config.get("classes", {})
    slots_per_day = _safe_get(classes, "slots_per_day", 0)
    days_per_week = _safe_get(classes, "days_per_week", 0)
    weeks_per_month = _safe_get(classes, "weeks_per_month", 4.3)
    fill_rate = _safe_get(classes, "fill_rate", 0)
    capacity = _safe_get(config, "capacity", 0)

    total_slots = slots_per_day * days_per_week * weeks_per_month

    pricing = config.get("pricing", {})
    class_price = _safe_get(pricing, "single_class_price", 0)
    discount_rate = _safe_get(pricing, "discount_rate", 0)
    payment_fee_rate = _safe_get(config, "payment_fee_rate", 0)
    trainer_payout_rate = _safe_get(config, "trainer_payout_rate", 0)
    variable_cost_per_attendee = _safe_get(config, "variable_cost_per_attendee", 0)

    corporate = config.get("corporate", {})
    corporate_days = _safe_get(corporate, "days_per_month", 0)
    corporate_day_rate = _safe_get(pricing, "corporate_day_rate", 0)
    corporate_variable_rate = _safe_get(pricing, "corporate_variable_cost_rate", 0)
    replace_public_slots = corporate.get("public_slots_replaced", True)

    effective_price = class_price * (1 - discount_rate)

    corporate_revenue = corporate_days * corporate_day_rate
    corporate_variable = corporate_revenue * corporate_variable_rate
    corporate_contribution = corporate_revenue - corporate_variable

    public_slots = max(total_slots - corporate_days * slots_per_day if replace_public_slots else total_slots, 0)
    avg_attendees = capacity * fill_rate
    total_attendees = public_slots * avg_attendees

    net_revenue = total_attendees * effective_price
    trainer_payout = net_revenue * trainer_payout_rate
    payment_fees = net_revenue * payment_fee_rate
    variable_costs = total_attendees * variable_cost_per_attendee
    variable_total = variable_costs + trainer_payout + payment_fees

    total_revenue = net_revenue + corporate_revenue
    total_variable_costs = variable_total + corporate_variable
    contribution_margin = total_revenue - total_variable_costs
    profit_before_tax = contribution_margin - fixed_costs

    contribution_per_attendee = effective_price * (1 - trainer_payout_rate - payment_fee_rate) - variable_cost_per_attendee
    break_even_fill_rate = None
    if contribution_per_attendee > 0 and public_slots * capacity > 0:
        required_attendees = max(fixed_costs - corporate_contribution, 0) / contribution_per_attendee
        break_even_fill_rate = required_attendees / (public_slots * capacity)

    return {
        "pnl": PnL(
            revenue=total_revenue,
            variable_costs=total_variable_costs,
            fixed_costs=fixed_costs,
            contribution_margin=contribution_margin,
            profit_before_tax=profit_before_tax,
            break_even_fill_rate=break_even_fill_rate,
        ).__dict__,
        "operating_assumptions": {
            "total_slots": total_slots,
            "public_slots": public_slots,
            "avg_attendees": avg_attendees,
            "total_attendees": total_attendees,
        },
        "corporate": {
            "revenue": corporate_revenue,
            "contribution": corporate_contribution,
        },
        "fixed_costs_detail": overheads,
    }


def aggregate_results(jewelry: Dict[str, Any], yoga: Dict[str, Any], retail: Dict[str, Any], tax: Dict[str, Any]) -> Dict[str, Any]:
    segments = [jewelry, yoga, retail]
    total_revenue = sum(item["pnl"]["revenue"] for item in segments)
    total_variable = sum(item["pnl"]["variable_costs"] for item in segments)
    total_fixed = sum(item["pnl"]["fixed_costs"] for item in segments)
    contribution_margin = total_revenue - total_variable
    profit_before_tax = contribution_margin - total_fixed

    profit_tax_rate = _safe_get(tax, "profit_tax_rate", 0)
    tax_expense = profit_before_tax * profit_tax_rate if profit_before_tax > 0 else 0
    profit_after_tax = profit_before_tax - tax_expense

    return {
        "revenue": total_revenue,
        "variable_costs": total_variable,
        "fixed_costs": total_fixed,
        "contribution_margin": contribution_margin,
        "profit_before_tax": profit_before_tax,
        "tax_expense": tax_expense,
        "profit_after_tax": profit_after_tax,
    }


def render_summary(results: Dict[str, Any]) -> str:
    return json.dumps(results, indent=2, ensure_ascii=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unit economics calculator for jewelry, yoga studio, and retail shop."
    )
    parser.add_argument("--config", type=Path, required=True, help="Path to JSON config file")
    args = parser.parse_args()

    with args.config.open() as f:
        config = json.load(f)

    jewelry = compute_jewelry(config.get("jewelry", {}))
    yoga = compute_yoga(config.get("yoga", {}))
    retail = compute_retail(config.get("retail", {}))
    tax = config.get("tax", {})

    aggregate = aggregate_results(jewelry, yoga, retail, tax)

    summary = {
        "currency": config.get("currency", "RUB"),
        "jewelry": jewelry,
        "yoga": yoga,
        "retail": retail,
        "aggregate": aggregate,
        "notes": {
            "profit_tax_rate": tax.get("profit_tax_rate", 0),
            "assumption": "All figures are monthly unless specified; break-even fill rate shown as share of capacity.",
        },
    }

    print(render_summary(summary))


if __name__ == "__main__":
    main()
