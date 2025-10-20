"""Config flow for Fluval Aquasky Bluetooth LED integration."""

import re
from typing import Any

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_MAC

from .const import CONF_BLE_DEVICE, DOMAIN

MAC_REGEX = r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MAC): str,
    }
)


class AquaskyLedConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flows for the integration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user initiated config flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_MAC]

            if not _is_mac_valid(address):
                errors["base"] = (
                    "Please enter a valid MAC address to the bluetooth device"
                )
            else:
                ble_device = bluetooth.async_ble_device_from_address(
                    hass=self.hass, address=address, connectable=True
                )

                await self.async_set_unique_id(ble_device.address)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=ble_device.name
                    or f"BLE#{ble_device.address.replace(':', '')}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


def _is_mac_valid(mac) -> bool:
    return re.match(MAC_REGEX, mac)
