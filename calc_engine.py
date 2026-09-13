"""
calc_engine.py — BESSopt deterministic techno-economic calculation engine.

Every function here is plain arithmetic. No AI model is involved in producing
these numbers — that's intentional. The vision/reasoning layer in this project
handles input parsing and report narration; the money math stays auditable.
"""

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Config: local market assumptions. Update these as prices change — this file
# is the single place sizing/costing assumptions live, so the rest of the app
# never hardcodes a number.
# ---------------------------------------------------------------------------

DIESEL_PRICE_PKR_PER_LITRE = 278.0          # update to current pump price
GENSET_FUEL_CONSUMPTION_L_PER_KWH = 0.32    # typical mid-size diesel genset
BESS_CAPEX_PKR_PER_KWH = 55000.0            # installed cost incl. inverter/PCS
BESS_OM_PCT_OF_CAPEX_PER_YEAR = 0.02        # annual O&M as % of CapEx
BATTERY_ROUND_TRIP_EFFICIENCY = 0.90
BATTERY_USABLE_DOD = 0.80                   # LFP — keep above ~20% reserve
BATTERY_CYCLE_LIFE = 4000                   # cycles at the DoD above
GRID_TARIFF_PKR_PER_KWH_DEFAULT = 45.0      # fallback if user doesn't supply


@dataclass
class SiteInputs:
    """What we ask the user for (via form or bill-photo extraction)."""
    daily_loadshedding_hours: float          # hours/day the grid is down
    average_load_kw: float                   # average load during outage
    genset_kva: Optional[float] = None       # for baseline comparison
    diesel_price_pkr_per_litre: float = DIESEL_PRICE_PKR_PER_LITRE
    grid_tariff_pkr_per_kwh: float = GRID_TARIFF_PKR_PER_KWH_DEFAULT
    analysis_years: int = 7


@dataclass
class SizingResult:
    recommended_bess_kwh: float
    recommended_inverter_kw: float


@dataclass
class FinancialResult:
    capex_pkr: float
    annual_om_pkr: float
    annual_diesel_baseline_pkr: float
    annual_bess_opex_pkr: float
    annual_savings_pkr: float
    payback_years: float
    roi_pct_over_horizon: float
    battery_useful_life_years: float


def size_bess(inputs: SiteInputs) -> SizingResult:
    """
    Size the battery to cover the load-shedding window at the site's average
    load, respecting usable depth-of-discharge so the battery isn't cycled
    into its unsafe range every day.
    """
    energy_needed_kwh = inputs.daily_loadshedding_hours * inputs.average_load_kw
    recommended_bess_kwh = energy_needed_kwh / BATTERY_USABLE_DOD
    # Inverter/PCS sized to the peak load with a small headroom margin.
    recommended_inverter_kw = round(inputs.average_load_kw * 1.15, 1)
    return SizingResult(
        recommended_bess_kwh=round(recommended_bess_kwh, 1),
        recommended_inverter_kw=recommended_inverter_kw,
    )


def diesel_baseline_annual_cost(inputs: SiteInputs) -> float:
    """What the site currently spends on diesel per year to cover the same
    outage window, used as the baseline BESS displaces."""
    daily_energy_kwh = inputs.daily_loadshedding_hours * inputs.average_load_kw
    litres_per_day = daily_energy_kwh * GENSET_FUEL_CONSUMPTION_L_PER_KWH
    annual_litres = litres_per_day * 365
    return annual_litres * inputs.diesel_price_pkr_per_litre


def bess_annual_opex(sizing: SizingResult, inputs: SiteInputs) -> float:
    """O&M cost plus the (small) round-trip efficiency loss cost, priced at
    the grid tariff since that's what recharges the battery."""
    capex = sizing.recommended_bess_kwh * BESS_CAPEX_PKR_PER_KWH
    om_cost = capex * BESS_OM_PCT_OF_CAPEX_PER_YEAR
    daily_energy_kwh = inputs.daily_loadshedding_hours * inputs.average_load_kw
    annual_energy_kwh = daily_energy_kwh * 365
    charging_loss_kwh = annual_energy_kwh * (1 - BATTERY_ROUND_TRIP_EFFICIENCY)
    charging_loss_cost = charging_loss_kwh * inputs.grid_tariff_pkr_per_kwh
    return om_cost + charging_loss_cost


def battery_useful_life_years(sizing: SizingResult, inputs: SiteInputs) -> float:
    """How many years the battery lasts at one full-depth cycle per day,
    before hitting its rated cycle life."""
    cycles_per_year = 365
    return round(BATTERY_CYCLE_LIFE / cycles_per_year, 1)


def run_financials(inputs: SiteInputs, sizing: SizingResult) -> FinancialResult:
    capex = sizing.recommended_bess_kwh * BESS_CAPEX_PKR_PER_KWH
    annual_om = bess_annual_opex(sizing, inputs)
    diesel_baseline = diesel_baseline_annual_cost(inputs)
    annual_savings = diesel_baseline - annual_om
    payback_years = capex / annual_savings if annual_savings > 0 else float("inf")

    horizon = inputs.analysis_years
    total_savings = annual_savings * horizon
    roi_pct = ((total_savings - capex) / capex) * 100 if capex > 0 else 0.0

    return FinancialResult(
        capex_pkr=round(capex, 0),
        annual_om_pkr=round(annual_om, 0),
        annual_diesel_baseline_pkr=round(diesel_baseline, 0),
        annual_bess_opex_pkr=round(annual_om, 0),
        annual_savings_pkr=round(annual_savings, 0),
        payback_years=round(payback_years, 2) if payback_years != float("inf") else -1,
        roi_pct_over_horizon=round(roi_pct, 1),
        battery_useful_life_years=battery_useful_life_years(sizing, inputs),
    )


def sensitivity_analysis(inputs: SiteInputs, sizing: SizingResult) -> dict:
    """Re-run the financials under a diesel-price spike and a tariff spike,
    so the report doesn't rest on one static assumption."""
    base = run_financials(inputs, sizing)

    diesel_up = SiteInputs(**{**inputs.__dict__, "diesel_price_pkr_per_litre": inputs.diesel_price_pkr_per_litre * 1.20})
    diesel_up_result = run_financials(diesel_up, sizing)

    tariff_up = SiteInputs(**{**inputs.__dict__, "grid_tariff_pkr_per_kwh": inputs.grid_tariff_pkr_per_kwh * 1.15})
    tariff_up_result = run_financials(tariff_up, sizing)

    return {
        "base_case": base,
        "diesel_price_up_20pct": diesel_up_result,
        "grid_tariff_up_15pct": tariff_up_result,
    }


def full_report(inputs: SiteInputs) -> dict:
    """The single entry point the app calls: takes validated inputs, returns
    everything needed to render the report."""
    sizing = size_bess(inputs)
    sensitivity = sensitivity_analysis(inputs, sizing)
    return {
        "inputs": inputs,
        "sizing": sizing,
        "financials": sensitivity["base_case"],
        "sensitivity": sensitivity,
    }
