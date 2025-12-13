"""DataUpdateCoordinator for NED Energy Forecast."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACTIVITY_CONSUMPTION,
    ACTIVITY_PRODUCTION,
    API_BASE_URL,
    API_ENDPOINT,
    CLASSIFICATION_FORECAST,
    DATA_TYPE_CONSUMPTION,
    DATA_TYPE_SOLAR,
    DATA_TYPE_WIND_OFFSHORE,
    DATA_TYPE_WIND_ONSHORE,
    DEFAULT_FORECAST_HOURS,
    DOMAIN,
    GRANULARITY_HOURLY,
    GRANULARITY_TIMEZONE_CET,
    SENSOR_TYPES,
)

_LOGGER = logging.getLogger(__name__)


class NEDEnergyDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching NED Energy data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api_key: str,
        forecast_hours: int = DEFAULT_FORECAST_HOURS,
    ) -> None:
        """Initialize."""
        self.api_key = api_key
        self.forecast_hours = forecast_hours
        self.platforms = []

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=1),
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        try:
            data: dict[str, Any] = {}
            
            for key, info in SENSOR_TYPES.items():
                if info.get("calculated"):
                    continue
                
                sensor_data = await self._fetch_sensor_data(
                    type_id=info["type_id"],
                    activity=info["activity"],
                )
                data[key] = sensor_data
                _LOGGER.debug("Fetched %d records for %s", len(sensor_data), key)
            
            # Calculate total renewable (wind + solar)
            if "wind_onshore" in data and "wind_offshore" in data and "solar" in data:
                onshore = data["wind_onshore"]
                offshore = data["wind_offshore"]
                solar = data["solar"]
                
                total_renewable: list[dict] = []
                for on_item, off_item, sol_item in zip(onshore, offshore, solar):
                    total_capacity = (
                        on_item["capacity"]
                        + off_item["capacity"]
                        + sol_item["capacity"]
                    )
                    total_renewable.append({
                        "capacity": total_capacity,
                        "timestamp": on_item["timestamp"],
                        "percentage": None,
                        "last_update": on_item.get("last_update"),
                    })
                
                data["total_renewable"] = total_renewable
            
            # Calculate coverage percentage
            if "total_renewable" in data and "consumption" in data:
                renewable = data["total_renewable"]
                consumption = data["consumption"]
                
                coverage: list[dict] = []
                for r_item, c_item in zip(renewable, consumption):
                    percentage = (
                        (r_item["capacity"] / c_item["capacity"] * 100)
                        if c_item["capacity"] > 0
                        else 0
                    )
                    coverage.append({
                        "capacity": round(percentage, 1),
                        "timestamp": r_item["timestamp"],
                        "percentage": None,
                        "last_update": r_item.get("last_update"),
                    })
                
                data["coverage_percentage"] = coverage
            
            # Calculate feed-in tariff: (duurzame opwek - verbruik) / 33
            if "total_renewable" in data and "consumption" in data:
                renewable = data["total_renewable"]
                consumption = data["consumption"]
                
                tariff: list[dict] = []
                for r_item, c_item in zip(renewable, consumption):
                    # Formule: (duurzame opwek - verbruik) / 33
                    tariff_value = (r_item["capacity"] - c_item["capacity"]) / 33
                    
                    tariff.append({
                        "capacity": round(tariff_value, 4),  # 4 decimalen voor precisie
                        "timestamp": r_item["timestamp"],
                        "percentage": None,
                        "last_update": r_item.get("last_update"),
                    })
                
                data["feed_in_tariff"] = tariff
            
            return data
            
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    async def _fetch_sensor_data(self, type_id: int, activity: int) -> list[dict]:
        """Fetch sensor data from the API."""
        url = f"{API_BASE_URL}{API_ENDPOINT}"
        
        now = datetime.now()
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(hours=self.forecast_hours)).strftime("%Y-%m-%d")
        
        headers = {
            "X-AUTH-TOKEN": self.api_key,
            "accept": "application/ld+json",
        }
        
        params = {
            "point": 0,
            "type": type_id,
            "granularity": GRANULARITY_HOURLY,
            "granularitytimezone": GRANULARITY_TIMEZONE_CET,
            "classification": CLASSIFICATION_FORECAST,
            "activity": activity,
            "validfrom[after]": start_date,
            "validfrom[strictly_before]": end_date,
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, headers=headers, params=params, timeout=30
                ) as response:
                    if response.status != 200:
                        _LOGGER.error(
                            "Failed to fetch data for type %s: HTTP %s",
                            type_id,
                            response.status,
                        )
                        return []
                    
                    data = await response.json()
                    records = data.get("hydra:member", [])
                    
                    if not records:
                        _LOGGER.warning("No data returned for type %s", type_id)
                        return []
                    
                    parsed: list[dict] = []
                    for record in records:
                        parsed.append({
                            "capacity": record.get("capacity", 0),
                            "timestamp": record.get("validfrom"),
                            "percentage": record.get("percentage"),
                            "last_update": record.get("lastupdate"),
                        })
                    
                    parsed.sort(key=lambda x: x["timestamp"] or "")
                    return parsed
                    
        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error while fetching data: %s", err)
            return []
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching data")
            return []
