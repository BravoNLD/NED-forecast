"""Constants for the NED Energy Forecast integration."""

DOMAIN = "ned_energy_forecast"

# API Configuration
API_BASE_URL = "https://api.ned.nl"
API_ENDPOINT = "/v1/utilizations"

# API Parameters
GRANULARITY_HOURLY = 60
GRANULARITY_TIMEZONE_CET = "CET"
CLASSIFICATION_FORECAST = "forecast"

# Activity types
ACTIVITY_PRODUCTION = 1
ACTIVITY_CONSUMPTION = 2

# Data types
DATA_TYPE_CONSUMPTION = 1
DATA_TYPE_SOLAR = 2
DATA_TYPE_WIND_ONSHORE = 3
DATA_TYPE_WIND_OFFSHORE = 4

# Default values
DEFAULT_FORECAST_HOURS = 48

# Sensor types
SENSOR_TYPES = {
    "consumption": {
        "name": "NED Forecast Consumption",
        "icon": "mdi:transmission-tower",
        "unit": "MW",
        "type_id": DATA_TYPE_CONSUMPTION,
        "activity": ACTIVITY_CONSUMPTION,
        "calculated": False,
    },
    "solar": {
        "name": "NED Forecast Solar",
        "icon": "mdi:solar-power",
        "unit": "MW",
        "type_id": DATA_TYPE_SOLAR,
        "activity": ACTIVITY_PRODUCTION,
        "calculated": False,
    },
    "wind_onshore": {
        "name": "NED Forecast Wind Onshore",
        "icon": "mdi:wind-turbine",
        "unit": "MW",
        "type_id": DATA_TYPE_WIND_ONSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "calculated": False,
    },
    "wind_offshore": {
        "name": "NED Forecast Wind Offshore",
        "icon": "mdi:turbine",
        "unit": "MW",
        "type_id": DATA_TYPE_WIND_OFFSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "calculated": False,
    },
    "total_renewable": {
        "name": "NED Forecast Total Renewable",
        "icon": "mdi:leaf",
        "unit": "MW",
        "calculated": True,
    },
    "coverage_percentage": {
        "name": "NED Forecast Coverage Percentage",
        "icon": "mdi:percent",
        "unit": "%",
        "calculated": True,
    },
    "feed_in_tariff": {
        "name": "NED Forecast Feed-in Tariff",
        "icon": "mdi:cash-multiple",
        "unit": "ratio",
        "calculated": True,
    },
}
