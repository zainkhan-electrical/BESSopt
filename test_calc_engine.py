"""
Checks for calc_engine.py and report_pdf.py.
Run with:  python test_calc_engine.py   (or: python -m pytest)
"""

from dataclasses import replace

from calc_engine import (
    BATTERY_ROUND_TRIP_EFFICIENCY, SiteInputs, build_report, diesel_cost_per_kwh,
    energy_profile, evaluate_config, summary_text,
)
from report_pdf import build_pdf
from resource_data import CITY_RESOURCES

KARACHI = CITY_RESOURCES["Karachi"]
GHARO = CITY_RESOURCES["Gharo / Thatta (Sindh wind corridor)"]


def site(city=KARACHI, **kw):
    base = dict(
        average_load_kw=25, daily_loadshedding_hours=6,
        solar_yield_kwh_per_kwp=city["solar_kwh_per_kwp"], wind_capacity_factor=city["wind_cf"],
    )
    base.update(kw)
    return SiteInputs(**base)


def test_baseline_matches_hand_calculation():
    inp = site()
    prof = energy_profile(inp)
    assert round(prof.total_kwh) == 25 * 12 * 330
    assert round(prof.outage_kwh) == 25 * 6 * 330
    base = evaluate_config(inp, "baseline")
    expected = prof.outage_kwh * diesel_cost_per_kwh(inp) + prof.grid_kwh * inp.grid_tariff_pkr_per_kwh
    assert abs(base.annual_cost - expected) < 1


def test_battery_recharge_energy_is_paid_for():
    # The battery's output has to be bought from the grid first, losses included.
    inp = site()
    prof = energy_profile(inp)
    bess = evaluate_config(inp, "bess")
    assert bess.diesel_cost == 0
    recharge_cost = prof.outage_kwh / BATTERY_ROUND_TRIP_EFFICIENCY * inp.grid_tariff_pkr_per_kwh
    assert abs(bess.grid_cost - prof.grid_kwh * inp.grid_tariff_pkr_per_kwh) < 1
    assert abs(bess.battery_charge_cost - recharge_cost) < 1
    assert abs(bess.annual_cost - (bess.grid_cost + bess.battery_charge_cost + bess.om_cost)) < 1


def test_wind_declined_where_resource_is_weak():
    rep = build_report(site(KARACHI, location_name="Karachi"))
    assert not rep.configs["wind_bess"].available
    assert not rep.configs["solar_wind_bess"].available
    assert "too weak" in rep.configs["wind_bess"].note
    assert rep.recommended_key not in ("wind_bess", "solar_wind_bess")


def test_wind_modelled_in_the_sindh_corridor():
    rep = build_report(site(GHARO, location_name="Gharo"))
    assert rep.configs["wind_bess"].available
    assert rep.configs["wind_bess"].wind_kw > 0


def test_roof_area_limits_solar_size():
    capped = evaluate_config(site(roof_area_m2=60), "solar_bess")
    assert capped.solar_kwp <= 10.0 + 1e-9


def test_dearer_diesel_shortens_payback():
    a = evaluate_config(site(), "bess").payback_years
    b = evaluate_config(site(diesel_price_pkr_per_litre=350), "bess").payback_years
    assert b < a


def test_battery_replacement_counted_on_long_horizon():
    assert evaluate_config(site(analysis_years=7), "bess").replacement_cost == 0
    assert evaluate_config(site(analysis_years=15), "bess").replacement_cost > 0


def test_no_recommendation_when_nothing_pays_back_in_time():
    rep = build_report(site(analysis_years=1))
    assert rep.recommended_key is None
    assert "staying on grid plus diesel" in summary_text(rep)


def test_no_load_shedding_means_no_battery_case():
    rep = build_report(site(daily_loadshedding_hours=0))
    assert rep.configs["bess"].bess_kwh == 0


def test_pdf_builds_for_both_outcomes():
    for inp in (site(GHARO, location_name="Gharo"), site(analysis_years=1)):
        pdf = build_pdf(build_report(inp))
        assert pdf[:5] == b"%PDF-" and len(pdf) > 3000


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("ok  ", t.__name__)
    print(f"All {len(tests)} tests passed.")
