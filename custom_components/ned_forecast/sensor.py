"""Sensor platform for NED Energy Forecast."""
from __future__ import annotations

from dataclasses import dataclass
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
        """Return the state of the sensor."""
        sensor_data = self.coordinator.data.get(self._key)
        if not sensor_data:
            return None

        # Get the most recent (first) record
        latest = sensor_data[0]
        value = latest.get("capacity")

        if isinstance(value, (int, float)):
            return round(float(value), 1)

        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional attributes."""
        sensor_data = self.coordinator.data.get(self._key)
        if not sensor_data:
            return None

        latest = sensor_data[0]

        attributes = {
            "last_updated": latest.get("timestamp"),
            "percentage": latest.get("percentage"),
            "api_last_update": latest.get("last_update"),
        }
        import logging
        _LOGGER = logging.getLogger(__name__)
        _LOGGER.warning(f"Total records available for {self._key}: {len(sensor_data)}")

        # Add forecast
        forecast_list = []
        for record in sensor_data:  # All available hours
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
