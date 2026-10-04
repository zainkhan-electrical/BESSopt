"""
resource_data.py - planning-level solar and wind values for Pakistani cities.

IMPORTANT: these are rough planning figures, not measurements. They exist so
the tool can compare options without asking the owner for data they don't
have. Before anyone signs a purchase order:
  - check solar yield for the exact site in PVGIS or NASA POWER
  - measure wind on site for at least a few months (small-wind results vary a
    lot from one street to the next)

solar_kwh_per_kwp : annual energy per kWp of PV, after typical system losses
wind_cf           : annual capacity factor for a small (under 100 kW) turbine
"""

OTHER_LABEL = "Other (enter my own values)"

CITY_RESOURCES = {
    "Karachi": {"solar_kwh_per_kwp": 1650, "wind_cf": 0.12},
    "Hyderabad": {"solar_kwh_per_kwp": 1650, "wind_cf": 0.12},
    "Gharo / Thatta (Sindh wind corridor)": {"solar_kwh_per_kwp": 1650, "wind_cf": 0.25},
    "Sukkur": {"solar_kwh_per_kwp": 1700, "wind_cf": 0.08},
    "Multan": {"solar_kwh_per_kwp": 1600, "wind_cf": 0.07},
    "Lahore": {"solar_kwh_per_kwp": 1500, "wind_cf": 0.06},
    "Faisalabad": {"solar_kwh_per_kwp": 1550, "wind_cf": 0.06},
    "Islamabad / Rawalpindi": {"solar_kwh_per_kwp": 1500, "wind_cf": 0.07},
    "Peshawar": {"solar_kwh_per_kwp": 1500, "wind_cf": 0.06},
    "Quetta": {"solar_kwh_per_kwp": 1750, "wind_cf": 0.10},
    "Gwadar": {"solar_kwh_per_kwp": 1700, "wind_cf": 0.18},
}

CITY_NAMES = list(CITY_RESOURCES.keys())
