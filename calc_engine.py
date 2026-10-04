"""
calc_engine.py - BESSopt v2 techno-economic engine.

Everything here is plain arithmetic. No AI model touches these numbers; the
vision model only reads bill photos, and the PDF/summary text is built from
the results below.

The model is an annual energy balance, not an hour-by-hour simulation. That
keeps it easy to check by hand, at the cost of some precision.

What it compares (all against the same baseline, grid + diesel backup):
  baseline         current setup, nothing new
  bess             battery only, recharged from the grid
  solar_bess       solar PV + battery
  wind_bess        wind + battery (only where the wind resource is usable)
  solar_wind_bess  solar + wind + battery

Simplifications worth knowing about:
  - Simple (undiscounted) payback and ROI. No price escalation, no panel
    degradation, no export credit for surplus power.
  - The battery is sized to carry the load-shedding window, so diesel use
    drops to zero in every battery configuration.
  - Solar and wind are sized to offset grid energy (and battery recharging),
    limited by roof area for solar and a 100 kW cap for wind.
  - All prices below are editable assumptions, not quotes.
"""

from dataclasses import dataclass, replace
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Assumptions. Change them here; nothing else in the app hardcodes a price.
# ---------------------------------------------------------------------------
DIESEL_PRICE_PKR_PER_LITRE = 278.0
GENSET_FUEL_L_PER_KWH = 0.32          # typical mid-size diesel genset
GENSET_OM_PKR_PER_KWH = 6.0           # genset servicing and wear
GRID_TARIFF_DEFAULT_PKR_PER_KWH = 45.0

BESS_CAPEX_PKR_PER_KWH = 55_000.0     # installed, includes inverter/PCS
BESS_OM_PCT_PER_YEAR = 0.02
BATTERY_ROUND_TRIP_EFFICIENCY = 0.90
BATTERY_USABLE_DOD = 0.80             # LFP, keep ~20% in reserve
BATTERY_CYCLE_LIFE = 4000
BATTERY_CALENDAR_LIFE_YEARS = 12
BATTERY_REPLACEMENT_COST_FACTOR = 0.70  # replacement priced at 70% of today's cost
INVERTER_HEADROOM = 1.15

SOLAR_CAPEX_PKR_PER_KWP = 130_000.0   # installed, includes inverter
SOLAR_OM_PCT_PER_YEAR = 0.015
SOLAR_AREA_M2_PER_KWP = 6.0

WIND_CAPEX_PKR_PER_KW = 750_000.0     # small turbines, installed
WIND_OM_PCT_PER_YEAR = 0.03
WIND_MAX_KW = 100.0
WIND_MIN_CAPACITY_FACTOR = 0.15       # below this, wind is not worth modelling
HOURS_PER_YEAR = 8760

CONFIG_ORDER = ["baseline", "bess", "solar_bess", "wind_bess", "solar_wind_bess"]
CONFIG_LABELS = {
    "baseline": "Current setup (grid + diesel)",
    "bess": "Battery only",
    "solar_bess": "Solar + battery",
    "wind_bess": "Wind + battery",
    "solar_wind_bess": "Solar + wind + battery",
}
CONFIG_SHORT_LABELS = {
    "baseline": "Current",
    "bess": "Battery",
    "solar_bess": "Solar+Batt",
    "wind_bess": "Wind+Batt",
    "solar_wind_bess": "Solar+Wind+Batt",
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SiteInputs:
    average_load_kw: float
    daily_loadshedding_hours: float
    operating_hours_per_day: float = 12.0
    operating_days_per_year: int = 330
    daytime_load_share: float = 0.8
    diesel_price_pkr_per_litre: float = DIESEL_PRICE_PKR_PER_LITRE
    grid_tariff_pkr_per_kwh: float = GRID_TARIFF_DEFAULT_PKR_PER_KWH
    analysis_years: int = 7
    solar_yield_kwh_per_kwp: float = 1600.0
    wind_capacity_factor: float = 0.10
    roof_area_m2: Optional[float] = None
    genset_kva: Optional[float] = None
    location_name: str = ""


@dataclass
class EnergyProfile:
    total_kwh: float
    outage_kwh: float
    grid_kwh: float
    daytime_kwh: float
    outage_hours: float


@dataclass
class ConfigResult:
    key: str
    label: str
    available: bool = True
    note: str = ""
    solar_kwp: float = 0.0
    wind_kw: float = 0.0
    bess_kwh: float = 0.0
    inverter_kw: float = 0.0
    capex_bess: float = 0.0
    capex_solar: float = 0.0
    capex_wind: float = 0.0
    capex_total: float = 0.0
    diesel_cost: float = 0.0
    grid_cost: float = 0.0
    battery_charge_cost: float = 0.0
    om_cost: float = 0.0
    annual_cost: float = 0.0
    annual_savings: float = 0.0
    payback_years: Optional[float] = None
    replacement_cost: float = 0.0
    net_benefit: float = 0.0
    roi_pct: Optional[float] = None
    solar_generation_kwh: float = 0.0
    wind_generation_kwh: float = 0.0
    renewable_share_pct: float = 0.0
    diesel_litres_avoided: float = 0.0


@dataclass
class Report:
    inputs: SiteInputs
    profile: EnergyProfile
    configs: Dict[str, ConfigResult]
    recommended_key: Optional[str]
    fastest_key: Optional[str]
    sensitivity: Dict[str, Dict[str, ConfigResult]]
    battery_life_years: float


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def energy_profile(inputs: SiteInputs) -> EnergyProfile:
    """Split the year's electricity use into outage hours and grid hours."""
    outage_h = max(0.0, min(inputs.daily_loadshedding_hours, inputs.operating_hours_per_day))
    days = inputs.operating_days_per_year
    total = inputs.average_load_kw * inputs.operating_hours_per_day * days
    outage = inputs.average_load_kw * outage_h * days
    return EnergyProfile(
        total_kwh=total,
        outage_kwh=outage,
        grid_kwh=total - outage,
        daytime_kwh=total * inputs.daytime_load_share,
        outage_hours=outage_h,
    )


def diesel_cost_per_kwh(inputs: SiteInputs) -> float:
    return GENSET_FUEL_L_PER_KWH * inputs.diesel_price_pkr_per_litre + GENSET_OM_PKR_PER_KWH


def battery_life_years(inputs: SiteInputs) -> float:
    """One full cycle per operating day until the rated cycle life is used up,
    capped by calendar life."""
    days = max(1, inputs.operating_days_per_year)
    return min(BATTERY_CYCLE_LIFE / days, BATTERY_CALENDAR_LIFE_YEARS)


def _baseline(inputs: SiteInputs, prof: EnergyProfile):
    diesel = prof.outage_kwh * diesel_cost_per_kwh(inputs)
    grid = prof.grid_kwh * inputs.grid_tariff_pkr_per_kwh
    return diesel, grid


# ---------------------------------------------------------------------------
# One configuration
# ---------------------------------------------------------------------------
def evaluate_config(inputs: SiteInputs, key: str) -> ConfigResult:
    prof = energy_profile(inputs)
    base_diesel, base_grid = _baseline(inputs, prof)
    baseline_annual = base_diesel + base_grid
    res = ConfigResult(key=key, label=CONFIG_LABELS[key])

    if key == "baseline":
        res.diesel_cost = base_diesel
        res.grid_cost = base_grid
        res.annual_cost = baseline_annual
        return res

    use_solar = key in ("solar_bess", "solar_wind_bess")
    use_wind = key in ("wind_bess", "solar_wind_bess")

    def _unavailable(reason: str) -> ConfigResult:
        res.available = False
        res.note = reason
        res.diesel_cost = base_diesel
        res.grid_cost = base_grid
        res.annual_cost = baseline_annual
        return res

    if use_wind and inputs.wind_capacity_factor < WIND_MIN_CAPACITY_FACTOR:
        return _unavailable(
            f"Wind resource too weak for a small turbine here "
            f"(capacity factor about {inputs.wind_capacity_factor * 100:.0f}%, "
            f"minimum {WIND_MIN_CAPACITY_FACTOR * 100:.0f}%)."
        )

    tariff = inputs.grid_tariff_pkr_per_kwh
    rte = BATTERY_ROUND_TRIP_EFFICIENCY

    # Battery: carries the load-shedding window, recharged between outages.
    bess_kwh = prof.outage_hours * inputs.average_load_kw / BATTERY_USABLE_DOD
    inverter_kw = inputs.average_load_kw * INVERTER_HEADROOM if bess_kwh > 0 else 0.0
    charge_need = prof.outage_kwh / rte  # kWh drawn to recharge each year

    # Solar: sized to the daytime load that the grid would otherwise supply,
    # plus battery recharging, then limited by roof area.
    solar_kwp = 0.0
    e_pv = 0.0
    if use_solar:
        target_kwh = min(prof.daytime_kwh, prof.grid_kwh + charge_need)
        kwp = target_kwh / inputs.solar_yield_kwh_per_kwp
        if inputs.roof_area_m2 and inputs.roof_area_m2 > 0:
            kwp = min(kwp, inputs.roof_area_m2 / SOLAR_AREA_M2_PER_KWP)
        solar_kwp = kwp
        e_pv = kwp * inputs.solar_yield_kwh_per_kwp
    pv_direct = min(e_pv, prof.daytime_kwh, prof.grid_kwh)
    pv_surplus = e_pv - pv_direct

    # Wind: runs around the clock, so only the share that lands inside
    # operating hours can serve the load directly. The rest can recharge the
    # battery.
    remaining_grid = prof.grid_kwh - pv_direct
    residual_charge = max(0.0, charge_need - pv_surplus)
    wind_kw = 0.0
    e_wind = 0.0
    coincidence = max(0.05, min(1.0, inputs.operating_hours_per_day / 24.0))
    if use_wind:
        e_target = remaining_grid / coincidence
        e_target += max(0.0, residual_charge - remaining_grid * (1 - coincidence) / coincidence)
        kw_per_kwh = 1.0 / (HOURS_PER_YEAR * inputs.wind_capacity_factor)
        wind_kw = min(e_target * kw_per_kwh, WIND_MAX_KW)
        e_wind = wind_kw * HOURS_PER_YEAR * inputs.wind_capacity_factor
        if wind_kw < 0.5:
            return _unavailable("Solar already covers the load wind could serve, so wind adds nothing here.")
    wind_direct = min(e_wind * coincidence, remaining_grid)
    wind_surplus = e_wind - wind_direct

    free_charge = min(pv_surplus + wind_surplus, charge_need)
    paid_charge = charge_need - free_charge
    grid_purchase = prof.grid_kwh - pv_direct - wind_direct

    res.solar_kwp = solar_kwp
    res.wind_kw = wind_kw
    res.bess_kwh = bess_kwh
    res.inverter_kw = inverter_kw
    res.solar_generation_kwh = e_pv
    res.wind_generation_kwh = e_wind

    res.capex_bess = bess_kwh * BESS_CAPEX_PKR_PER_KWH
    res.capex_solar = solar_kwp * SOLAR_CAPEX_PKR_PER_KWP
    res.capex_wind = wind_kw * WIND_CAPEX_PKR_PER_KW
    res.capex_total = res.capex_bess + res.capex_solar + res.capex_wind

    res.diesel_cost = 0.0
    res.grid_cost = grid_purchase * tariff
    res.battery_charge_cost = paid_charge * tariff
    res.om_cost = (
        res.capex_bess * BESS_OM_PCT_PER_YEAR
        + res.capex_solar * SOLAR_OM_PCT_PER_YEAR
        + res.capex_wind * WIND_OM_PCT_PER_YEAR
    )
    res.annual_cost = res.grid_cost + res.battery_charge_cost + res.om_cost
    res.annual_savings = baseline_annual - res.annual_cost
    res.payback_years = res.capex_total / res.annual_savings if res.annual_savings > 0 and res.capex_total > 0 else None

    life = battery_life_years(inputs)
    replacements = 0
    if bess_kwh > 0 and inputs.analysis_years > life:
        replacements = int(-(-inputs.analysis_years // life)) - 1  # ceil(years/life) - 1
    res.replacement_cost = replacements * res.capex_bess * BATTERY_REPLACEMENT_COST_FACTOR
    res.net_benefit = res.annual_savings * inputs.analysis_years - res.capex_total - res.replacement_cost
    res.roi_pct = res.net_benefit / res.capex_total * 100 if res.capex_total > 0 else None

    renewable_kwh = pv_direct + wind_direct + free_charge * rte
    res.renewable_share_pct = renewable_kwh / prof.total_kwh * 100 if prof.total_kwh > 0 else 0.0
    res.diesel_litres_avoided = prof.outage_kwh * GENSET_FUEL_L_PER_KWH
    return res


# ---------------------------------------------------------------------------
# Whole report
# ---------------------------------------------------------------------------
def build_report(inputs: SiteInputs) -> Report:
    prof = energy_profile(inputs)
    configs = {k: evaluate_config(inputs, k) for k in CONFIG_ORDER}

    candidates: List[ConfigResult] = [
        r for k, r in configs.items()
        if k != "baseline" and r.available and r.annual_savings > 0
        and r.payback_years is not None and r.payback_years <= inputs.analysis_years
        and r.net_benefit > 0
    ]
    recommended = max(candidates, key=lambda r: r.net_benefit).key if candidates else None
    fastest = min(candidates, key=lambda r: r.payback_years).key if candidates else None

    sensitivity: Dict[str, Dict[str, ConfigResult]] = {}
    for k, r in configs.items():
        if k == "baseline" or not r.available:
            continue
        sensitivity[k] = {
            "base": r,
            "diesel_up_20": evaluate_config(
                replace(inputs, diesel_price_pkr_per_litre=inputs.diesel_price_pkr_per_litre * 1.20), k),
            "tariff_up_15": evaluate_config(
                replace(inputs, grid_tariff_pkr_per_kwh=inputs.grid_tariff_pkr_per_kwh * 1.15), k),
        }

    return Report(
        inputs=inputs,
        profile=prof,
        configs=configs,
        recommended_key=recommended,
        fastest_key=fastest,
        sensitivity=sensitivity,
        battery_life_years=battery_life_years(inputs),
    )


# ---------------------------------------------------------------------------
# Formatting and plain-language summary (shared by the app and the PDF)
# ---------------------------------------------------------------------------
def fmt_pkr(x: float) -> str:
    if abs(x) >= 1_000_000:
        return f"PKR {x / 1_000_000:,.2f} million"
    return f"PKR {x:,.0f}"


def fmt_pkr_plain(x: float) -> str:
    return f"{x:,.0f}"


def fmt_years(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:.1f} yrs"


def system_description(r: ConfigResult) -> str:
    parts = []
    if r.solar_kwp > 0:
        parts.append(f"{r.solar_kwp:,.1f} kWp solar")
    if r.wind_kw > 0:
        parts.append(f"{r.wind_kw:,.1f} kW wind")
    if r.bess_kwh > 0:
        parts.append(f"{r.bess_kwh:,.0f} kWh battery")
    return ", ".join(parts) if parts else "No new equipment"


def summary_text(report: Report) -> str:
    inp = report.inputs
    years = inp.analysis_years
    out = []

    rec = report.configs.get(report.recommended_key) if report.recommended_key else None
    if rec:
        out.append(
            f"For this site, {rec.label.lower()} comes out best over {years} years. "
            f"It costs {fmt_pkr(rec.capex_total)} up front, saves about "
            f"{fmt_pkr(rec.annual_savings)} a year and pays itself back in roughly "
            f"{rec.payback_years:.1f} years. By year {years} you would be about "
            f"{fmt_pkr(rec.net_benefit)} ahead of the current setup."
        )
        fast = report.configs.get(report.fastest_key) if report.fastest_key else None
        if fast and fast.key != rec.key:
            out.append(
                f"{fast.label} pays back sooner ({fast.payback_years:.1f} years) "
                f"but earns less over the full period."
            )
        sens = report.sensitivity.get(rec.key)
        if sens:
            d, t = sens["diesel_up_20"], sens["tariff_up_15"]
            out.append(
                f"If diesel gets 20% dearer, payback becomes {fmt_years(d.payback_years)}. "
                f"If grid tariffs rise 15%, it becomes {fmt_years(t.payback_years)}."
            )
    else:
        out.append(
            f"None of the options pays itself back within {years} years at these loads "
            f"and prices, so staying on grid plus diesel is the cheaper choice for now. "
            f"A longer horizon, dearer diesel or a bigger daytime load could change that."
        )

    wind_notes = [r.note for k, r in report.configs.items() if k in ("wind_bess", "solar_wind_bess") and not r.available and r.note]
    if wind_notes:
        place = f" at {inp.location_name}" if inp.location_name else ""
        if "too weak" in wind_notes[0]:
            out.append(
                f"Wind was left out{place}: the resource is too weak for a small turbine "
                f"(capacity factor about {inp.wind_capacity_factor * 100:.0f}%)."
            )
    return " ".join(out)


ASSUMPTIONS: List[str] = [
    f"Diesel: {GENSET_FUEL_L_PER_KWH} L per kWh generated, plus PKR {GENSET_OM_PKR_PER_KWH:.0f} per kWh for genset servicing.",
    f"Battery (LFP): PKR {BESS_CAPEX_PKR_PER_KWH:,.0f} per kWh installed, {BATTERY_USABLE_DOD * 100:.0f}% usable depth of discharge, "
    f"{BATTERY_ROUND_TRIP_EFFICIENCY * 100:.0f}% round-trip efficiency, {BATTERY_CYCLE_LIFE:,} cycles, "
    f"{BESS_OM_PCT_PER_YEAR * 100:.0f}% yearly O&M. Replacement, if needed inside the horizon, costs {BATTERY_REPLACEMENT_COST_FACTOR * 100:.0f}% of today's price.",
    f"Solar: PKR {SOLAR_CAPEX_PKR_PER_KWP:,.0f} per kWp installed, {SOLAR_OM_PCT_PER_YEAR * 100:.1f}% yearly O&M, about {SOLAR_AREA_M2_PER_KWP:.0f} m2 of roof per kWp.",
    f"Wind: PKR {WIND_CAPEX_PKR_PER_KW:,.0f} per kW installed, {WIND_OM_PCT_PER_YEAR * 100:.0f}% yearly O&M, capped at {WIND_MAX_KW:.0f} kW, "
    f"and only modelled where the capacity factor is at least {WIND_MIN_CAPACITY_FACTOR * 100:.0f}%.",
    "Payback and ROI are simple (undiscounted). No price escalation, panel degradation or export credit for surplus power.",
    "Solar and wind values per city are planning figures. Check solar yield in PVGIS or NASA POWER, and measure wind on site before buying.",
    "Fixed grid charges, taxes beyond the all-in tariff, and financing costs are not modelled.",
]
