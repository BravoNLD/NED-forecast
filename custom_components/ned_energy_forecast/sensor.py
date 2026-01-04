"""Sensor platform for NED Energy Forecast."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

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
        device_class = SensorDeviceClass.POWER if info.get("unit") == "MW" else None

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
        import logging
        _LOGGER = logging.getLogger(__name__)
        
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
            current_record = sensor_data[0]
        
        value = current_record.get("capacity")

        if isinstance(value, (int, float)):
            return round(float(value), 1)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        sensor_data = self.coordinator.data.get(self._key)
        if not sensor_data:
            return None

        # Gebruik dezelfde logica om het huidige record te vinden
        now = datetime.now()
        current_record = None
        
        for record in sensor_data:
            timestamp_str = record.get("timestamp")
            if timestamp_str:
                try:
                    ts_clean = timestamp_str.replace('Z', '+00:00')
                    record_time = datetime.fromisoformat(ts_clean)
                    
                    if now.tzinfo is None and record_time.tzinfo is not None:
                        record_time = record_time.replace(tzinfo=None)
                    
                    if record_time <= now:
                        current_record = record
                    else:
                        break
                except (ValueError, AttributeError):
                    continue
        
        if current_record is None:
            current_record = sensor_data[0]

        attributes = {
            "last_updated": current_record.get("timestamp"),
            "percentage": current_record.get("percentage"),
            "api_last_update": current_record.get("last_update"),
        }
        
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.debug(f"Total records available for {self._key}: {len(sensor_data)}")

        # Add forecast - alle toekomstige waarden
        forecast_list = []
        for record in sensor_data:
            forecast_list.append(
                {
                    "datetime": record.get("timestamp"),
                    "value": round(float(record.get("capacity", 0)), 1),
                }
            )

        if forecast_list:
            attributes["forecast"] = forecast_list
            attributes["forecast_hours"] = len(forecast_list)

        return attributes
