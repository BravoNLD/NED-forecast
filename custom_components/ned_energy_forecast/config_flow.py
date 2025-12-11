"""Config flow for NED Energy Forecast integration."""
import logging
from typing import Any
import aiohttp
import voluptuous as vol
from datetime import datetime, timedelta

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    API_BASE_URL,
    API_ENDPOINT,
    CONF_API_KEY,
    CONF_FORECAST_HOURS,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_FORECAST_HOURS, default=168): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=336)
        ),
    }
)


async def test_api_connection(api_key: str) -> bool:
    """Test if we can connect to the NED API."""
    url = f"{API_BASE_URL}{API_ENDPOINT}"
    
    now = datetime.now()
    start_date = now.strftime("%Y-%m-%d")
    end_date = (now + timedelta(hours=24)).strftime("%Y-%m-%d")
    
    headers = {
        "X-AUTH-TOKEN": api_key,
        "accept": "application/ld+json",
    }
    
    params = {
        "point": 0,
        "type": 1,  # Wind onshore
        "granularity": 5,  # ✅ HOURLY (was: "hour")
        "granularitytimezone": 1,  # ✅ CET (was: "Europe/Amsterdam")
        "classification": 1,  # FORECAST
        "activity": 1,  # PRODUCTION
        "validfrom[after]": start_date,
        "validfrom[strictly_before]": end_date,
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params, timeout=30
            ) as response:
                if response.status == 401:
                    _LOGGER.error("Invalid API key")
                    return False
                
                if response.status == 403:
                    _LOGGER.error("API access forbidden")
                    return False
                
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        "NED API test failed with status %s: %s",
                        response.status,
                        error_text,
                    )
                    return False
                
                data = await response.json()
                records = data.get("hydra:member", [])
                
                if not records:
                    _LOGGER.warning("API test returned no data")
                    return False
                
                _LOGGER.info("API test successful, got %d records", len(records))
                return True
                
    except aiohttp.ClientError as err:
        _LOGGER.error("Connection error during API test: %s", err)
        return False
    except Exception as err:
        _LOGGER.exception("Unexpected error during API test")
        return False


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NED Energy Forecast."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                # Test the API connection
                if not await test_api_connection(user_input[CONF_API_KEY]):
                    errors["base"] = "cannot_connect"
                else:
                    # Create the entry
                    return self.async_create_entry(
                        title="NED Energy Forecast",
                        data=user_input,
                    )
            except Exception:
                _LOGGER.exception("Unexpected exception during setup")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
