"""Data update coordinator for NED Energy Forecast."""

import logging
from datetime import datetime, timedelta
import asyncio
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.recorder import get_instance, history
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    API_BASE_URL,
    API_ENDPOINT,
    CONF_API_KEY,
    CONF_FORECAST_HOURS,
    CONF_PRICE_SENSOR,
    CLASSIFICATION_FORECAST,
    GRANULARITY_HOURLY,
    GRANULARITY_TIMEZONE_CET,
    SENSOR_TYPES,
    DEFAULT_SCAN_INTERVAL,
    SOLAR_NOT_IN_CONSUMPTION_GW,
    REFIT_TIME,
    ROLLING_WINDOW_DAYS,
    MIN_DATAPOINTS,
)
from .linear_regression import LinearRegression

_LOGGER = logging.getLogger(__name__)


class NEDEnergyDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Class to manage fetching NED Energy data from the API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry  # ✅ Bewaar entry reference voor later
        self.api_key: str = entry.data[CONF_API_KEY]
        
        # ✅ GEFIXED: Haal opties uit entry.options (niet entry.data)
        self.forecast_hours: int = entry.options.get(CONF_FORECAST_HOURS, 48)
        self.price_sensor: str | None = entry.options.get(CONF_PRICE_SENSOR)
        
        # Linear regression model (cache tussen refits)
        self.lr_model: LinearRegression | None = None
        self.last_fit_time: datetime | None = None

        # Model Metrics
        self.model_r2_score: float | None = None
        self.model_datapoints: int | None = None
        
        # Cancel handles voor scheduled tasks
        self._cancel_hourly_update = None
        self._cancel_daily_refit = None

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
                    solar_on_grid = solar_val * SOLAR_NOT_IN_CONSUMPTION_GW
                    total_renewable = wind_on + wind_off + solar_on_grid
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

                    # ========== EPEX SPOTPRIJS FORECAST MET LINEAR REGRESSION ==========
                    # ✅ Alleen berekenen als price_sensor is geconfigureerd
                    if self.price_sensor:
                        await self._calculate_epex_forecast_lr(data)
                    else:
                        _LOGGER.debug("Price sensor niet geconfigureerd, EPEX forecast overgeslagen")
                    
                    # ✅ NIEUW: Voeg R² score toe als sensor
                    if self.model_r2_score is not None:
                        data["model_r2_score"] = [
                            {
                                "capacity": round(self.model_r2_score, 4),
                                "timestamp": datetime.now().isoformat(),
                                "percentage": None,
                            }
                        ]
                        
                        # Voeg extra metadata toe als attributes
                        if self.model_datapoints is not None:
                            data["model_r2_score"][0]["datapoints"] = self.model_datapoints
                        if self.last_fit_time:
                            data["model_r2_score"][0]["last_fit"] = self.last_fit_time.isoformat()

                except (KeyError, ValueError, IndexError, TypeError) as err:
                    _LOGGER.warning("Could not calculate derived values: %s", err)

            return data

        except Exception as err:
            _LOGGER.exception("Error fetching data")
            raise UpdateFailed(f"Error communicating with NED API: {err}") from err

    async def _calculate_epex_forecast_lr(self, data: dict[str, Any]) -> None:
        """
        Bereken EPEX spotprijs forecast met Linear Regression.
        
        Features:
        - consumption_gw
        - wind_onshore_gw
        - wind_offshore_gw
        - solar_gw
        - net_demand_gw (derived: consumption - total_renewable)
        
        Target:
        - epex_price (ct/kWh) uit de user-geconfigureerde prijssensor
        """
        try:
            # ✅ Check of price sensor is ingesteld
            if not self.price_sensor:
                _LOGGER.debug("Price sensor niet ingesteld, EPEX forecast overgeslagen")
                return
            
            # Fit model dagelijks om 02:07 (of bij eerste run)
            if self.lr_model is None or self._should_refit():
                await self._fit_lr_model()
            
            # Als model nog steeds None is, gebruik fallback formule
            if self.lr_model is None:
                _LOGGER.warning("LR model niet beschikbaar, gebruik fallback formule")
                self._calculate_epex_fallback(data)
                return
            
            # Voorspel prijzen voor alle forecast timestaps
            wind_onshore = data.get("wind_onshore", [])
            wind_offshore = data.get("wind_offshore", [])
            solar = data.get("solar", [])
            consumption = data.get("consumption", [])

            if not all([wind_onshore, wind_offshore, solar, consumption]):
                _LOGGER.warning("EPEX forecast overgeslagen: niet alle bron-data beschikbaar")
                return

            # Maak features voor elk tijdstip
            epex_forecast: list[dict] = []
            
            # Combineer data op timestamp
            combined: dict[str, dict[str, float]] = {}
            
            for record in wind_onshore:
                ts = record.get("timestamp")
                if ts:
                    combined[ts] = {"wind_onshore": float(record.get("capacity", 0))}

            for record in wind_offshore:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["wind_offshore"] = float(record.get("capacity", 0))

            for record in solar:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["solar"] = float(record.get("capacity", 0))

            for record in consumption:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["consumption"] = float(record.get("capacity", 0))

            # Voorspel voor elk compleet record
            for timestamp, values in sorted(combined.items()):
                if all(k in values for k in ["wind_onshore", "wind_offshore", "solar", "consumption"]):
                    # Bereken features
                    solar_on_grid = values["solar"] * SOLAR_NOT_IN_CONSUMPTION_GW
                    total_renewable = values["wind_onshore"] + values["wind_offshore"] + solar_on_grid
                    net_demand = values["consumption"] - total_renewable
                    
                    # Feature vector: [consumption, wind_on, wind_off, solar, net_demand]
                    X = [[
                        values["consumption"],
                        values["wind_onshore"],
                        values["wind_offshore"],
                        values["solar"],
                        net_demand
                    ]]
                    
                    # Voorspel prijs
                    price_predictions = self.lr_model.predict(X)
                    price_prediction = price_predictions[0]
                    
                    # Begrens tussen -5 en 50 ct/kWh (realistisch bereik)
                    price_prediction = max(-5.0, min(50.0, price_prediction))
                    
                    epex_forecast.append({
                        "capacity": round(price_prediction, 3),
                        "timestamp": timestamp,
                        "percentage": None,
                    })

            # Sla resultaat op
            if epex_forecast:
                data["forecast_epex_price"] = epex_forecast
                _LOGGER.info(
                    "EPEX LR forecast: %d datapunten, huidige prijs: %.3f ct/kWh (model age: %s)",
                    len(epex_forecast),
                    epex_forecast[0]["capacity"],
                    (datetime.now() - self.last_fit_time) if self.last_fit_time else "nooit"
                )
            else:
                _LOGGER.warning("EPEX LR forecast resulteerde in geen data")

        except Exception as err:
            _LOGGER.error("Fout bij EPEX LR forecast: %s", err, exc_info=True)
            # Fallback naar oude formule
            self._calculate_epex_fallback(data)

    def _calculate_epex_fallback(self, data: dict[str, Any]) -> None:
        """Fallback formule als LR model niet beschikbaar is."""
        try:
            wind_onshore = data.get("wind_onshore", [])
            wind_offshore = data.get("wind_offshore", [])
            solar = data.get("solar", [])
            consumption = data.get("consumption", [])

            combined: dict[str, dict[str, float]] = {}

            for record in wind_onshore:
                ts = record.get("timestamp")
                if ts:
                    combined[ts] = {"wind_onshore": float(record.get("capacity", 0))}

            for record in wind_offshore:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["wind_offshore"] = float(record.get("capacity", 0))

            for record in solar:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["solar"] = float(record.get("capacity", 0))

            for record in consumption:
                ts = record.get("timestamp")
                if ts and ts in combined:
                    combined[ts]["consumption"] = float(record.get("capacity", 0))

            epex_forecast: list[dict] = []

            for timestamp, values in sorted(combined.items()):
                if all(k in values for k in ["wind_onshore", "wind_offshore", "solar", "consumption"]):
                    solar_on_grid = values["solar"] * SOLAR_NOT_IN_CONSUMPTION_GW
                    total_renewable = values["wind_onshore"] + values["wind_offshore"] + solar_on_grid
                    restlast_gw = values["consumption"] - total_renewable
                    
                    epex_price = (1.08 * restlast_gw) + 0.45

                    epex_forecast.append({
                        "capacity": round(epex_price, 3),
                        "timestamp": timestamp,
                        "percentage": None,
                    })

            if epex_forecast:
                data["forecast_epex_price"] = epex_forecast
                _LOGGER.info("EPEX fallback formule gebruikt: %d datapunten", len(epex_forecast))

        except Exception as err:
            _LOGGER.error("Fout bij fallback EPEX berekening: %s", err)

    def _should_refit(self) -> bool:
        """Check of model opnieuw gefit moet worden."""
        if self.last_fit_time is None:
            return True
        
        # Check of het > 24 uur geleden is
        time_since_fit = datetime.now() - self.last_fit_time
        return time_since_fit > timedelta(hours=24)

    async def _fit_lr_model(self) -> None:
        """Fit Linear Regression model op basis van 30 dagen historische data uit recorder."""
        try:
            # ✅ Check of price sensor is ingesteld
            if not self.price_sensor:
                _LOGGER.info("Price sensor niet ingesteld, model fit overgeslagen")
                return
            
            _LOGGER.info("Start Linear Regression model fit...")
        
            # Haal 30 dagen historische data op uit recorder
            end_time = dt_util.now()
            start_time = end_time - timedelta(days=ROLLING_WINDOW_DAYS)
        
            # Entity IDs van onze eigen sensoren
            entity_ids = [
                "sensor.ned_forecast_consumption",
                "sensor.ned_forecast_wind_onshore",
                "sensor.ned_forecast_wind_offshore",
                "sensor.ned_forecast_solar",
                self.price_sensor,  # User-configured prijssensor
            ]
        
            # Verzamel alle data per entity
            historical_records: dict[str, list] = {}
        
            for entity_id in entity_ids:
                entity_history = await get_instance(self.hass).async_add_executor_job(
                    history.state_changes_during_period,
                    self.hass,
                    start_time,
                    end_time,
                    str(entity_id),
                    False,
                    True,
                    None
                )
            
                if entity_id in entity_history:
                    historical_records[entity_id] = entity_history[entity_id]
                    _LOGGER.debug(f"Opgehaald {len(entity_history[entity_id])} records voor {entity_id}")
                else:
                    _LOGGER.warning(f"Geen history gevonden voor {entity_id}")
                    historical_records[entity_id] = []
        
            # Bouw feature matrix X en target vector y
            X_list = []
            y_list = []
        
            # Parse consumption als baseline timestamps
            consumption_entity = "sensor.ned_forecast_consumption"
            if consumption_entity not in historical_records or not historical_records[consumption_entity]:
                _LOGGER.error("Geen consumption history gevonden, kan model niet fitten")
                return
        
            # Maak dict voor snelle lookup
            wind_on_dict = {state.last_updated: state for state in historical_records.get("sensor.ned_forecast_wind_onshore", [])}
            wind_off_dict = {state.last_updated: state for state in historical_records.get("sensor.ned_forecast_wind_offshore", [])}
            solar_dict = {state.last_updated: state for state in historical_records.get("sensor.ned_forecast_solar", [])}
            price_dict = {state.last_updated: state for state in historical_records.get(self.price_sensor, [])}
        
            for cons_state in historical_records[consumption_entity]:
                try:
                    ts = cons_state.last_updated
                
                    # Probeer waarden te vinden binnen 5 minuten van timestamp
                    consumption = float(cons_state.state)
                
                    # Zoek matching states (binnen 5 min)
                    wind_on_val = self._find_closest_state(wind_on_dict, ts, timedelta(minutes=5))
                    wind_off_val = self._find_closest_state(wind_off_dict, ts, timedelta(minutes=5))
                    solar_val = self._find_closest_state(solar_dict, ts, timedelta(minutes=5))
                    price_val = self._find_closest_state(price_dict, ts, timedelta(minutes=5))
                
                    if None in [wind_on_val, wind_off_val, solar_val, price_val]:
                        continue
                
                    # Bereken net_demand
                    solar_on_grid = solar_val * SOLAR_NOT_IN_CONSUMPTION_GW
                    total_renewable = wind_on_val + wind_off_val + solar_on_grid
                    net_demand = consumption - total_renewable
                
                    # Feature vector
                    X_list.append([consumption, wind_on_val, wind_off_val, solar_val, net_demand])
                    y_list.append(price_val)
                
                except (ValueError, TypeError, AttributeError):
                    continue
        
            if len(X_list) < MIN_DATAPOINTS:
                _LOGGER.warning(
                    f"Niet genoeg datapunten voor fit: {len(X_list)} < {MIN_DATAPOINTS}. Model niet gefit."
                )
                return
        
            # Fit model met eigen LinearRegression implementatie
            self.lr_model = LinearRegression()
            self.lr_model.fit(X_list, y_list)
            self.last_fit_time = datetime.now()
        
            # ✅ R² score berekenen en opslaan
            self.model_r2_score = self.lr_model.score(X_list, y_list)
            self.model_datapoints = len(X_list)
        
            _LOGGER.info(
                f"✅ Linear Regression model gefit op {len(X_list)} datapunten. R² score: {self.model_r2_score:.4f}"
            )
            _LOGGER.debug(f"Coëfficiënten: {self.lr_model.coefficients}, Intercept: {self.lr_model.intercept}")
        
        except Exception as err:
            _LOGGER.error(f"Fout bij fitten LR model: {err}", exc_info=True)
            self.lr_model = None
            self.model_r2_score = None
            self.model_datapoints = None

    def _find_closest_state(self, state_dict: dict, target_time: datetime, max_delta: timedelta) -> float | None:
        """Vind de dichtstbijzijnde state binnen max_delta."""
        closest_state = None
        closest_delta = max_delta
        
        for ts, state in state_dict.items():
            delta = abs(ts - target_time)
            if delta < closest_delta:
                closest_delta = delta
                closest_state = state
        
        if closest_state is None:
            return None
        
        try:
            return float(closest_state.state)
        except (ValueError, TypeError):
            return None

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

    @callback
    def _schedule_hourly_update(self) -> None:
        """Schedule update op hele uren (xx:00)."""
        async def _update_at_hour():
            while True:
                now = datetime.now()
                # Bereken tijd tot volgende hele uur
                next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
                wait_seconds = (next_hour - now).total_seconds()
                
                _LOGGER.debug(f"Volgende hourly update over {wait_seconds:.0f} seconden ({next_hour})")
                await asyncio.sleep(wait_seconds)
                
                # Trigger update
                await self.async_refresh()
        
        # Start task
        self._cancel_hourly_update = self.hass.async_create_task(_update_at_hour())

    @callback
    def _schedule_daily_refit(self) -> None:
        """Schedule dagelijkse refit om 02:07."""
        async def _refit_at_time():
            while True:
                now = datetime.now()
                
                # Bereken tijd tot volgende 02:07
                refit_hour, refit_minute = map(int, REFIT_TIME.split(":"))
                next_refit = now.replace(hour=refit_hour, minute=refit_minute, second=0, microsecond=0)
                
                # Als 02:07 vandaag al geweest is, plan voor morgen
                if next_refit <= now:
                    next_refit += timedelta(days=1)
                
                wait_seconds = (next_refit - now).total_seconds()
                
                _LOGGER.info(f"Volgende model refit gepland over {wait_seconds / 3600:.1f} uur ({next_refit})")
                await asyncio.sleep(wait_seconds)
                
                # Force refit
                _LOGGER.info("Start scheduled model refit...")
                await self._fit_lr_model()
                
                # Trigger update om nieuwe prijzen te berekenen
                await self.async_refresh()
        
        # Start task
        self._cancel_daily_refit = self.hass.async_create_task(_refit_at_time())

    async def async_shutdown(self) -> None:
        """Cleanup bij shutdown."""
        if self._cancel_hourly_update:
            self._cancel_hourly_update.cancel()
        if self._cancel_daily_refit:
            self._cancel_daily_refit.cancel()

    async def async_config_entry_first_refresh(self) -> None:
        """First refresh na setup - start schedulers."""
        await super().async_config_entry_first_refresh()
        
        # Start schedulers
        self._schedule_hourly_update()
        self._schedule_daily_refit()
        
        # ✅ Alleen refit als price sensor is ingesteld
        if self.price_sensor:
            await self._fit_lr_model()
        else:
            _LOGGER.info("Price sensor niet ingesteld, model fit overgeslagen bij startup")
