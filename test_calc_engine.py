"""
Basic sanity checks for calc_engine.py — run with: python -m pytest tests/
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from calc_engine import SiteInputs, size_bess, run_financials, full_report


def test_sizing_scales_with_load_and_hours():
    small = SiteInputs(daily_loadshedding_hours=4, average_load_kw=10)
    big = SiteInputs(daily_loadshedding_hours=8, average_load_kw=20)
    assert size_bess(big).recommended_bess_kwh > size_bess(small).recommended_bess_kwh


def test_higher_diesel_price_shortens_payback():
    base = SiteInputs(daily_loadshedding_hours=6, average_load_kw=25, diesel_price_pkr_per_litre=278)
    expensive_diesel = SiteInputs(daily_loadshedding_hours=6, average_load_kw=25, diesel_price_pkr_per_litre=350)

    sizing = size_bess(base)
    base_fin = run_financials(base, sizing)
    expensive_fin = run_financials(expensive_diesel, sizing)

    assert expensive_fin.payback_years < base_fin.payback_years


def test_full_report_returns_all_sections():
    inputs = SiteInputs(daily_loadshedding_hours=6, average_load_kw=25)
    report = full_report(inputs)
    assert "sizing" in report
    assert "financials" in report
    assert "sensitivity" in report
    assert report["financials"].capex_pkr > 0


if __name__ == "__main__":
    test_sizing_scales_with_load_and_hours()
    test_higher_diesel_price_shortens_payback()
    test_full_report_returns_all_sections()
    print("All tests passed.")
