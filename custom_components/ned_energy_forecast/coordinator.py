"""Data update coordinator for NED Energy Forecast."""

import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.components.recorder import get_instance, history
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_time_change

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
    SOLAR_ON_GRID_FRACTION,
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
                    solar_on_grid = solar_val * SOLAR_ON_GRID_FRACTION
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
                    solar_on_grid = values["solar"] * SOLAR_ON_GRID_FRACTION
                    renewables_total = values["wind_onshore"] + values["wind_offshore"] + solar_on_grid
                    residual = values["consumption"] - renewables_total
                    
                    # Feature vector: [consumption, wind_on, wind_off, solar_on_grid]
                    X = [[residual]]
                    
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
                    solar_on_grid = values["solar"] * SOLAR_ON_GRID_FRACTION
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
    
            # ========== HOURLY BUCKETING ==========
            def bucket_states_by_hour(states: list) -> dict[datetime, float]:
                """Bucket states naar hele uren, return dict {hour: avg_value}."""
                hour_buckets: dict[datetime, list[float]] = {}
            
                for state in states:
                    try:
                        # Align timestamp naar hele uur (floor)
                        hour = state.last_updated.replace(minute=0, second=0, microsecond=0)
                        value = float(state.state)
                    
                        if hour not in hour_buckets:
                            hour_buckets[hour] = []
                        hour_buckets[hour].append(value)
                    
                    except (ValueError, TypeError, AttributeError):
                        continue
            
                # Average per uur (als er meerdere records in 1 uur zijn)
                return {
                    hour: sum(values) / len(values)
                    for hour, values in hour_buckets.items()
                }
        
            # Bucket alle entities naar uren
            consumption_hourly = bucket_states_by_hour(
                historical_records.get("sensor.ned_forecast_consumption", [])
            )
            wind_on_hourly = bucket_states_by_hour(
                historical_records.get("sensor.ned_forecast_wind_onshore", [])
            )
            wind_off_hourly = bucket_states_by_hour(
                historical_records.get("sensor.ned_forecast_wind_offshore", [])
            )
            solar_hourly = bucket_states_by_hour(
                historical_records.get("sensor.ned_forecast_solar", [])
            )
            price_hourly = bucket_states_by_hour(
                historical_records.get(self.price_sensor, [])
            )
        
            # Debug: toon bucketed counts
            _LOGGER.debug(
                "Hourly bucketing: consumption=%d, wind_on=%d, wind_off=%d, solar=%d, price=%d uren",
                len(consumption_hourly),
                len(wind_on_hourly),
                len(wind_off_hourly),
                len(solar_hourly),
                len(price_hourly),
            )
        
            # ========== MATCHING + SOLAR=0 IMPUTATION ==========
            X_list = []
            y_list = []
        
            # ⭐ FIX 1: Tracking variabelen VOOR de loop initialiseren
            solar_real_count = 0
            solar_imputed_count = 0
        
            # ⭐ FIX 2: Skip_reasons zonder solar keys (solar wordt geïmputeerd)
            skip_reasons = {
                "missing_wind_on": 0,
                "missing_wind_off": 0,
                "missing_price": 0,
            }
        
            total_consumption_hours = len(consumption_hourly)
            matched_hours = 0
        
            # Itereer over alle consumption uren (baseline)
            for hour, consumption in sorted(consumption_hourly.items()):
                # Probeer alle features te vinden voor dit uur
                wind_on = wind_on_hourly.get(hour)
                wind_off = wind_off_hourly.get(hour)
                solar = solar_hourly.get(hour)
                price = price_hourly.get(hour)
            
                # ⭐ SOLAR IMPUTATION: Als solar missing, behandel als 0.0 (nacht)
                if solar is None:
                    solar = 0.0
                    solar_imputed_count += 1
                else:
                    solar_real_count += 1
            
                # Wind en price zijn nog steeds skip-redenen
                if wind_on is None:
                    skip_reasons["missing_wind_on"] += 1
                if wind_off is None:
                    skip_reasons["missing_wind_off"] += 1
                if price is None:
                    skip_reasons["missing_price"] += 1
            
                # ⭐ FIX 3: Skip alleen als wind OF price ontbreekt (solar is nu altijd gevuld)
                if None in [wind_on, wind_off, price]:
                    continue
                
                # Alle features aanwezig: bereken net_demand en voeg toe
                try:
                    solar_on_grid = solar * SOLAR_ON_GRID_FRACTION
                    renewables_total = wind_on + wind_off + solar_on_grid
                    residual = consumption - renewables_total
                
                    # Feature vector: [consumption, wind_on, wind_off, solar, net_demand]
                    X_list.append([residual])
                    y_list.append(price)
                
                    matched_hours += 1
                
                except (ValueError, TypeError):
                    continue
        
            # ========== DEBUG METRICS ==========
            # Coverage per feature (% van consumption uren waar feature aanwezig is)
            coverage_wind_on = (
                (total_consumption_hours - skip_reasons["missing_wind_on"]) 
                / total_consumption_hours * 100
            ) if total_consumption_hours > 0 else 0
        
            coverage_wind_off = (
                (total_consumption_hours - skip_reasons["missing_wind_off"]) 
                / total_consumption_hours * 100
            ) if total_consumption_hours > 0 else 0
        
            # ⭐ FIX 4: Solar coverage met real vs imputed breakdown
            coverage_solar_total = 100.0  # Altijd 100% (real + imputed)
            coverage_solar_real = (
                solar_real_count / total_consumption_hours * 100
            ) if total_consumption_hours > 0 else 0
        
            coverage_price = (
                (total_consumption_hours - skip_reasons["missing_price"]) 
                / total_consumption_hours * 100
            ) if total_consumption_hours > 0 else 0
        
            _LOGGER.info(
                "Feature coverage: wind_on=%.1f%%, wind_off=%.1f%%, "
                "solar=%.1f%% (%d real + %d imputed=0), price=%.1f%%",
                coverage_wind_on,
                coverage_wind_off,
                coverage_solar_total,
                solar_real_count,
                solar_imputed_count,
                coverage_price,
            )
        
            # ⭐ FIX 5: Expliciet log solar imputation
            if solar_imputed_count > 0:
                _LOGGER.info(
                    "🌙 Imputed solar=0.0 for %d hours (%.1f%%, likely night periods)",
                    solar_imputed_count,
                    (solar_imputed_count / total_consumption_hours * 100) if total_consumption_hours > 0 else 0
                )
        
            _LOGGER.debug(
                "Skip reasons: wind_on=%d, wind_off=%d, price=%d (van %d uren)",
                skip_reasons["missing_wind_on"],
                skip_reasons["missing_wind_off"],
                skip_reasons["missing_price"],
                total_consumption_hours,
            )
        
            # ========== MODEL FIT ==========
            if len(X_list) < MIN_DATAPOINTS:
                _LOGGER.warning(
                    f"Niet genoeg datapunten voor fit: {len(X_list)} < {MIN_DATAPOINTS}. Model niet gefit."
                )
            
                # ⭐ AANGEPASTE TIP: Solar is nu geen bottleneck meer
                if skip_reasons["missing_wind_on"] > total_consumption_hours * 0.3:
                    _LOGGER.info("TIP: Wind onshore coverage is laag. Check sensor configuratie.")
                elif skip_reasons["missing_wind_off"] > total_consumption_hours * 0.3:
                    _LOGGER.info("TIP: Wind offshore coverage is laag. Check sensor configuratie.")
                elif skip_reasons["missing_price"] > total_consumption_hours * 0.3:
                    _LOGGER.info("TIP: Price sensor coverage is laag. Check sensor configuratie.")
                else:
                    _LOGGER.info("TIP: Overweeg langere history periode (verhoog ROLLING_WINDOW_DAYS).")
            
                return
    
            # Fit model met eigen LinearRegression implementatie
            self.lr_model = LinearRegression()
            self.lr_model.fit(X_list, y_list)
            self.last_fit_time = datetime.now()
    
            # ✅ R² score berekenen en opslaan
            self.model_r2_score = self.lr_model.score(X_list, y_list)
            self.model_datapoints = len(X_list)
    
            _LOGGER.info(
                f"✅ Linear Regression model gefit op {len(X_list)} datapunten "
                f"(matched {matched_hours}/{total_consumption_hours} uren = {matched_hours/total_consumption_hours*100:.1f}%). "
                f"R² score: {self.model_r2_score:.4f}"
            )
            _LOGGER.debug(f"Model: price = {self.lr_model.intercept:.4f} + "f"{self.lr_model.coefficients[0]:.4f} * residual_gw")
    
        except Exception as err:
            _LOGGER.error(f"Fout bij fitten LR model: {err}", exc_info=True)
            self.lr_model = None
            self.model_r2_score = None
            self.model_datapoints = None

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
            # ✅ Gebruik HA centrale sessie voor connection pooling/timeouts
            session = aiohttp_client.async_get_clientsession(self.hass)
        
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
        """Schedule update op hele uren (xx:00) via HA time tracker."""
        
        async def _handle_hourly_update(now: datetime) -> None:
            """Callback voor elk heel uur."""  
            _LOGGER.debug("Hourly update geactiveerd op %s", now)
            await self.async_refresh()
        
        # Track elk heel uur (minute=0, second=0)
        self._cancel_hourly_update = async_track_time_change(
            self.hass,
            _handle_hourly_update,
            minute=0,
            second=0
        )

        _LOGGER.info("Hourly updates gescheduled op elk heel uur (:00)")

    @callback
    def _schedule_daily_refit(self) -> None:
        """Schedule dagelijks refit om 02:07 via HA time tracker."""

        async def _handle_daily_refit(now: datetime) -> None:
            """Callback voor dagelijkse model refit."""
            _LOGGER.info("Daily model refit geactiveerd op %s", now)

            await self._fit_lr_model()

            # Trigger update om nieuwe forecast te genereren met nieuw model
            await self.async_refresh()

        # Parse REFIT_TIME uit const.py (bijv "02:07")
        refit_hour, refit_minute = map(int, REFIT_TIME.split(":"))

        # Track dagelijks op 02:07 (hour=2, minute=7)
        self._cancel_daily_refit = async_track_time_change(
            self.hass,
            _handle_daily_refit,
            hour=refit_hour,
            minute=refit_minute,
            second=0
        )

        _LOGGER.info(
            "Daily model refit gescheduled op %02d:%02d (tijd uit config: %s)",
            refit_hour,
            refit_minute,
            REFIT_TIME
        )
                
                
    async def async_shutdown(self) -> None:
        """Cleanup bij shutdown - remove time tracking listeners."""
        # Cancel handles zijn nu callables (CALLBACK_TYPE)
        if self._cancel_hourly_update:
            self._cancel_hourly_update()
            _LOGGER.debug("Hourly update listener verwijderd")

        if self._cancel_daily_refit:
            self._cancel_daily_refit()
            _LOGGER.debug("Daily refit listener verwijderd")

    def start_background_schedulers(self) -> None:
        """Start background schedulers AFTER first refresh is complete."""
        _LOGGER.info("Starting background schedulers...")
        self._schedule_hourly_update()
        self._schedule_daily_refit()

    async def async_config_entry_first_refresh(self) -> None:
        """First refresh na setup - start schedulers."""
        await super().async_config_entry_first_refresh()
        
        # ✅ Alleen refit als price sensor is ingesteld
        if self.price_sensor:
            await self._fit_lr_model()
        else:
            _LOGGER.info("Price sensor niet ingesteld, model fit overgeslagen bij startup")
