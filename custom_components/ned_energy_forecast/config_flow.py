"""Config flow for NED Energy Forecast integration."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_FORECAST_HOURS,
    CONF_PRICE_SENSOR,
    API_BASE_URL,
    API_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

async def validate_api_key(hass: HomeAssistant, api_key: str) -> bool:
    """Validate the API key by making a test request."""
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    headers = {
        "X-AUTH-TOKEN": api_key,
        "accept": "application/ld+json",
    }
    params = {
        "point": 0,
        "type": 1,  # Wind onshore
        "granularity": 5,
        "granularitytimezone": 1,
        "classification": 1,
        "activity": 1,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params, timeout=10) as response:
                return response.status == 200
    except Exception as err:
        _LOGGER.error("Error validating API key: %s", err)
        return False


class NEDEnergyForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NED Energy Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Validate API key
                if not await validate_api_key(self.hass, user_input[CONF_API_KEY]):
                    errors["base"] = "invalid_auth"
                else:
                    # Store API key temporarily and move to next step
                    self._api_key = user_input[CONF_API_KEY]
                    self._forecast_hours = user_input.get(CONF_FORECAST_HOURS, 144)
                    return await self.async_step_price_sensor()

            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(CONF_FORECAST_HOURS, default=144): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=168)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_price_sensor(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle price sensor selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Valideer of de gekozen sensor bestaat
            price_sensor = user_input[CONF_PRICE_SENSOR]
            state = self.hass.states.get(price_sensor)
            
            if state is None:
                errors["base"] = "sensor_not_found"
            else:
                # Create entry met alle configuratie
                return self.async_create_entry(
                    title="NED Energy Forecast",
                    data={
                        CONF_API_KEY: self._api_key,
                        CONF_FORECAST_HOURS: self._forecast_hours,
                        CONF_PRICE_SENSOR: price_sensor,
                    },
                )

        return self.async_show_form(
            step_id="price_sensor",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRICE_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
            description_placeholders={
                "description": "Selecteer de EPEX prijssensor die gebruikt wordt voor het trainen van het voorspellingsmodel. Dit kan een kale EPEX spotprijs zijn, of je eigen afrekenprijs van je energieprovider."
            },
            errors=errors,
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
