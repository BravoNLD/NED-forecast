"""Config flow for NED Energy Forecast integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    NAME,
    CONF_PRICE_SENSOR,
    CONF_FORECAST_HOURS,
)

_LOGGER = logging.getLogger(__name__)


class NEDEnergyForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NED Energy Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Basic validation
            api_key = user_input.get(CONF_API_KEY, "").strip()
            
            if not api_key:
                errors[CONF_API_KEY] = "api_key_required"
            else:
                # Create the entry
                await self.async_set_unique_id(f"{DOMAIN}_{api_key[:8]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=NAME,
                    data={
                        CONF_API_KEY: api_key,
                    },
                    options={
                        CONF_PRICE_SENSOR: user_input.get(CONF_PRICE_SENSOR),
                        CONF_FORECAST_HOURS: user_input.get(CONF_FORECAST_HOURS, 48),
                    },
                )

        # Schema for user input
        data_schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): cv.string,
                vol.Optional(CONF_PRICE_SENSOR): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Optional(CONF_FORECAST_HOURS, default=48): vol.All(
                    vol.Coerce(int), vol.Range(min=12, max=168)
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> NEDEnergyForecastOptionsFlow:
        """Get the options flow for this handler."""
        return NEDEnergyForecastOptionsFlow(config_entry)


class NEDEnergyForecastOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for NED Energy Forecast."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_PRICE_SENSOR,
                    default=self.config_entry.options.get(CONF_PRICE_SENSOR),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain="sensor",
                    )
                ),
                vol.Optional(
                    CONF_FORECAST_HOURS,
                    default=self.config_entry.options.get(CONF_FORECAST_HOURS, 48),
                ): vol.All(vol.Coerce(int), vol.Range(min=12, max=168)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )
