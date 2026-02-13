"""Sensor platform for NED Energy Forecast."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, SENSOR_TYPES
from .coordinator import NEDEnergyDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class NEDSensorEntityDescription(SensorEntityDescription):
    """Describes NED sensor entity."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NED Energy sensors from a config entry."""
    coordinator: NEDEnergyDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = []

    for key, info in SENSOR_TYPES.items():
        # Set device class for MW sensors
        device_class = None  # MW unit, geen device_class om statistics te ondersteunen

        entities.append(
            NEDEnergySensor(
                coordinator=coordinator,
                key=key,
                description=NEDSensorEntityDescription(
                    key=key,
                    name=info["name"],
                    icon=info["icon"],
                    native_unit_of_measurement=info.get("unit"),
                    device_class=device_class,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
            )
        )

    async_add_entities(entities)


class NEDEnergySensor(CoordinatorEntity[NEDEnergyDataUpdateCoordinator], SensorEntity):
    """Representation of a NED Energy sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NEDEnergyDataUpdateCoordinator,
        key: str,
        description: NEDSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._key = key
        self.sensor_type = key  # ✅ GEFIXED: sensor_type toevoegen
        self._attr_unique_id = f"ned_energy_forecast_{key}"

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self._key in self.coordinator.data
            and bool(self.coordinator.data[self._key])
        )

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor - current value based on timestamp."""
        sensor_data = self.coordinator.data.get(self._key)
        if not sensor_data:
            return None

        # Vind het record dat het dichtst bij het huidige moment ligt
        now = datetime.now()
        
        # Zoek naar het meest recente record dat niet in de toekomst ligt
        current_record = None
        for record in sensor_data:
            timestamp_str = record.get("timestamp")
            if timestamp_str:
                try:
                    # Parse de timestamp - probeer verschillende formaten
                    # Verwijder 'Z' en vervang met timezone info
                    ts_clean = timestamp_str.replace('Z', '+00:00')
                    record_time = datetime.fromisoformat(ts_clean)
                    
                    # Maak record_time naive als now ook naive is
                    if now.tzinfo is None and record_time.tzinfo is not None:
                        record_time = record_time.replace(tzinfo=None)
                    
                    # Als dit record in het verleden of heden ligt
                    if record_time <= now:
                        current_record = record
                    else:
                        # We zijn bij toekomstige records aangekomen, stop
                        break
                except (ValueError, AttributeError) as err:
                    _LOGGER.debug(f"Could not parse timestamp {timestamp_str}: {err}")
                    continue
        
        # Als we geen huidig record vonden, neem het eerste record
        if current_record is None:
            _LOGGER.debug(f"No current record found for {self._key}, using first record")
            current_record = sensor_data[0] if sensor_data else None
        
        if current_record is None:
            return None
            
        value = current_record.get("capacity")

        if isinstance(value, (int, float)):
            return round(float(value), 1)

        # Fallback naar 0 i.p.v. None voor statistics compatibility
        _LOGGER.debug(f"No valid capacity for {self._key}, returning 0")
        return 0.0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        if not self.coordinator.data:
            return {}

        sensor_data = self.coordinator.data.get(self.sensor_type, [])
        if not sensor_data:
            return {}

        attributes = {}

        # ✅ Speciale attributes voor model_r2_score sensor
        if self.sensor_type == "model_r2_score" and sensor_data:
            latest = sensor_data[0]
        
            # Training dataset info
            if "datapoints" in latest:
                attributes["training_datapoints"] = latest["datapoints"]
        
            # Last fit timestamp
            if "last_fit" in latest:
                attributes["last_fit_time"] = latest["last_fit"]
        
            # Model coefficients (indien beschikbaar)
            if self.coordinator.lr_model:
                attributes["model_intercept"] = round(self.coordinator.lr_model.intercept, 4)
                attributes["model_coefficients"] = [round(c, 4) for c in self.coordinator.lr_model.coefficients]
                attributes["feature_names"] = [
                    "residual_gw"
                ]
        
            return attributes

        # Voor forecast sensoren: voeg forecast data toe
        if len(sensor_data) > 1:
            forecast_list = []
            for record in sensor_data[1:]:  # Skip first (current)
                forecast_list.append(
                    {
                        "datetime": record.get("timestamp"),
                        "value": record.get("capacity"),
                    }
                )
        
            attributes["forecast"] = forecast_list
            attributes["forecast_points"] = len(forecast_list)

        # First en last update timestamps
        if sensor_data:
            first = sensor_data[0]
            last = sensor_data[-1]
        
            if first.get("timestamp"):
                attributes["first_forecast_time"] = first["timestamp"]
            if last.get("timestamp"):
                attributes["last_forecast_time"] = last["timestamp"]
            if first.get("last_update"):
                attributes["last_api_update"] = first["last_update"]

        return attributes
