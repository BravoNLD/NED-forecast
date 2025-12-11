"""Constants for the NED Energy Forecast integration."""
from datetime import timedelta

DOMAIN = "ned_energy_forecast"
NAME = "NED Energy Forecast"
API_BASE_URL = "https://api.ned.nl/v1"
API_ENDPOINT = "/utilizations"
DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
CONF_API_KEY = "api_key"
CONF_FORECAST_HOURS = "forecast_hours"

# NED API Data Types
DATA_TYPE_WIND_ONSHORE = 1
DATA_TYPE_SOLAR = 2
DATA_TYPE_WIND_OFFSHORE = 51
DATA_TYPE_CONSUMPTION = 59

# NED API Classifications
CLASSIFICATION_FORECAST = 1

# NED API Activities
ACTIVITY_PRODUCTION = 1
ACTIVITY_CONSUMPTION = 2

# NED API Granularity
GRANULARITY_HOURLY = 5
GRANULARITY_TIMEZONE_CET = 1

# Sensor definitions
SENSOR_TYPES = {
    "wind_onshore": {
        "name": "NED Forecast Wind Onshore",
        "icon": "mdi:wind-turbine",
        "type_id": DATA_TYPE_WIND_ONSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
    },
    "wind_offshore": {
        "name": "NED Forecast Wind Offshore",
        "icon": "mdi:wind-turbine",
        "type_id": DATA_TYPE_WIND_OFFSHORE,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
    },
    "solar": {
        "name": "NED Forecast Solar",
        "icon": "mdi:solar-power",
        "type_id": DATA_TYPE_SOLAR,
        "activity": ACTIVITY_PRODUCTION,
        "unit": "MW",
    },
    "consumption": {
        "name": "NED Forecast Consumption",
        "icon": "mdi:transmission-tower",
        "type_id": DATA_TYPE_CONSUMPTION,
        "activity": ACTIVITY_CONSUMPTION,
        "unit": "MW",
    },
    "total_renewable": {
        "name": "NED Forecast Total Renewable",
        "icon": "mdi:leaf",
        "calculated": True,
        "unit": "MW",
    },
    "coverage_percentage": {
        "name": "NED Forecast Renewable Covverage",
        "icon": "mdi:percent",
        "calculated": True,
        "unit": "%",
    },
}
