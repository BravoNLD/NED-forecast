"""Data update coordinator for NED Energy Forecast."""

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    API_BASE_URL,
    API_ENDPOINT,
    CONF_API_KEY,
    CONF_FORECAST_HOURS,
    CLASSIFICATION_FORECAST,
    GRANULARITY_HOURLY,
    GRANULARITY_TIMEZONE_CET,
    SENSOR_TYPES,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class NEDEnergyDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching NED Energy data from the API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.api_key: str = entry.data[CONF_API_KEY]
        self.forecast_hours: int = entry.data.get(CONF_FORECAST_HOURS, 168)

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from API."""
        try:
            data: dict[str, Any] = {}

            # Fetch for each non-calculated sensor
            for key, info in SENSOR_TYPES.items():
                if info.get("calculated"):
                    continue

                sensor_data = await self._fetch_sensor_data(
                    type_id=info["type_id"],
                    activity=info["activity"],
                )
                data[key] = sensor_data

                if sensor_data:
                    _LOGGER.debug(
                        "Fetched %d records for %s (current: %.1f GW)",
                        len(sensor_data),
                        key,
                        sensor_data[0]["capacity"]
                    )

            # Calculate total renewable & coverage if we have all four
            if all(k in data and data[k] for k in ("wind_onshore", "wind_offshore", "solar", "consumption")):
                try:
                    # Get current (first) values
                    wind_on = float(data["wind_onshore"][0]["capacity"])
                    wind_off = float(data["wind_offshore"][0]["capacity"])
                    solar_val = float(data["solar"][0]["capacity"])
                    consumption = float(data["consumption"][0]["capacity"])

                    # Get timestamp from any sensor
                    ts = data["wind_onshore"][0]["timestamp"]

                    # Calculate totals
                    total_renewable = wind_on + wind_off + solar_val
                    coverage_pct = (total_renewable / consumption * 100) if consumption > 0 else 0.0

                    # Store as single-item lists for consistency
                    data["total_renewable"] = [
                        {
                            "capacity": round(total_renewable, 1),
                            "timestamp": ts,
                            "percentage": None,
                        }
                    ]

                    data["coverage_percentage"] = [
                        {
                            "capacity": round(coverage_pct, 1),
                            "timestamp": ts,
                            "percentage": round(coverage_pct, 1),
                        }
                    ]

                    _LOGGER.info(
                        "Energy summary: Renewable %.1f GW / Consumption %.1f GW = %.1f%% coverage",
                        total_renewable,
                        consumption,
                        coverage_pct,
                    )

                    # ========== EPEX SPOTPRIJS BEREKENING ==========
                    # Bereken: prijs = (1.27 * restlast_gw) + 1.5
                    self._calculate_epex_forecast(data)

                except (KeyError, ValueError, IndexError, TypeError) as err:
                    _LOGGER.warning("Could not calculate derived values: %s", err)

            return data

        except Exception as err:
            _LOGGER.exception("Error fetching data")
            raise UpdateFailed(f"Error communicating with NED API: {err}") from err

    def _calculate_epex_forecast(self, data: dict[str, Any]) -> None:
        """
        Bereken EPEX spotprijs forecast op basis van formule:
        prijs (ct/kWh) = (1.27 * restlast_gw) + 1.5
        
        Waarbij:
        - restlast_GW = consumptie - (wind_onshore + wind_offshore + solar)
        - consumptie_GW = consumption
        """
        try:
            # Haal alle timeseries op
            wind_onshore = data.get("wind_onshore", [])
            wind_offshore = data.get("wind_offshore", [])
            solar = data.get("solar", [])
            consumption = data.get("consumption", [])

            # Check of alle series data hebben
            if not all([wind_onshore, wind_offshore, solar, consumption]):
                _LOGGER.warning("EPEX berekening overgeslagen: niet alle bron-data beschikbaar")
                return

            # Maak een dict met timestamp als key om data te combineren
            combined: dict[str, dict[str, float]] = {}

            # Verzamel wind onshore
            for record in wind_onshore:
                ts = record.get("timestamp")
                if ts:
                    combined[ts] = {"wind_onshore": float(record.get("capacity", 0))}

            # Voeg wind offshore toe
            for record in wind_offshore:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["wind_offshore"] = float(record.get("capacity", 0))

            # Voeg solar toe
            for record in solar:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["solar"] = float(record.get("capacity", 0))

            # Voeg consumption toe
            for record in consumption:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["consumption"] = float(record.get("capacity", 0))

            # Bereken EPEX voor elk tijdstip waar we alle 4 waardes hebben
            epex_forecast: list[dict] = []

            for timestamp, values in sorted(combined.items()):
                # Controleer of alle waardes aanwezig zijn
                if all(k in values for k in ["wind_onshore", "wind_offshore", "solar", "consumption"]):
                    # Bereken totale hernieuwbare opwek
                    total_renewable = values["wind_onshore"] + values["wind_offshore"] + values["solar"]
                    
                    # Bereken restlast (consumptie - hernieuwbare opwek)
                    restlast_gw = values["consumption"] - total_renewable
                    consumptie_gw = values["consumption"]
                    
                    # Nieuwe formule: prijs = 1.27 × restlast_GW + 1.5
                    epex_price = (1.27 * restlast_gw) + 1.5

                    epex_forecast.append({
                        "capacity": round(epex_price, 3),  # EPEX prijs in ct/kWh, 3 decimalen
                        "timestamp": timestamp,
                        "percentage": None,
                    })

            # Sla resultaat op
            if epex_forecast:
                data["epex_price_forecast"] = epex_forecast
                _LOGGER.info(
                    "EPEX forecast berekend: %d datapunten, huidige prijs: %.3f ct/kWh (restlast: %.1f GW)",
                    len(epex_forecast),
                    epex_forecast[0]["capacity"],
                    values["consumption"] - (values["wind_onshore"] + values["wind_offshore"] + values["solar"])
                )
            else:
                _LOGGER.warning("EPEX berekening resulteerde in geen data")

        except Exception as err:
            _LOGGER.error("Fout bij berekenen EPEX forecast: %s", err, exc_info=True)

    async def _fetch_sensor_data(self, type_id: int, activity: int) -> list[dict]:
        """Fetch data for a specific sensor from the API."""
        url = f"{API_BASE_URL}{API_ENDPOINT}"

        # NED API expects dates in format: YYYY-MM-DD
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
                    if response.status == 401:
                        raise UpdateFailed("Invalid API key")
                    if response.status == 403:
                        raise UpdateFailed("API access forbidden - check your API key")

                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "NED API returned status %s for type %s: %s",
                            response.status,
                            type_id,
                            error_text,
                        )
                        return []

                    data = await response.json()
                    records = data.get("hydra:member", [])

                    if not records:
                        _LOGGER.warning("No data returned for type %s", type_id)
                        return []

                    parsed: list[dict] = []
                    for record in records:
                        # ⚡ API geeft capacity in Watt, we willen GW
                        capacity_watt = float(record.get("capacity", 0))
                        capacity_gw = capacity_watt / 1000000.0

                        parsed.append(
                            {
                                "capacity": capacity_gw,  # Converted to GW
                                "timestamp": record.get("validfrom"),
                                "percentage": record.get("percentage"),
                                "last_update": record.get("lastupdate"),
                            }
                        )

                    # Sort by timestamp (oudste eerst = chronologisch)
                    parsed.sort(key=lambda x: x["timestamp"] or "")

                    return parsed

        except aiohttp.ClientError as err:
            _LOGGER.error("Connection error fetching data for type %s: %s", type_id, err)
            return []
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching data for type %s", type_id)
            return []
