"""Light entity for the Fluval Aquasky Bluetooth LED integration."""

import logging

from homeassistant.components import bluetooth
from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .aquasky.led import BLELed

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> bool:
    """Set up light entity."""

    address = entry.data[CONF_MAC]
    ble_device = bluetooth.async_ble_device_from_address(
        hass=hass, address=address, connectable=True
    )
    async_add_entities([AquaskyLightEntity(BLELed(ble_device=ble_device))])

    return True


class AquaskyLightEntity(LightEntity):
    """Light entity to control the bluetooth LED."""

    should_poll = True

    def __init__(self, led: BLELed) -> None:
        """Initialise entity."""
        self._attr_name = led.ble_device.name
        self._attr_unique_id = led.ble_device.address
        self._led = led

    @property
    def supported_color_modes(self):
        return {ColorMode.BRIGHTNESS}

    @property
    def color_mode(self):
        return ColorMode.BRIGHTNESS

    @property
    def is_on(self) -> bool | None:
        return self._led.is_on

    @property
    def brightness(self) -> int | None:
        pct = self._led.brightness_pct
        return round(pct * 255) if pct is not None else None

    async def async_turn_on(self, **kwargs) -> None:
        """Turn on LED, optionally setting brightness."""
        if ATTR_BRIGHTNESS in kwargs:
            fluval_val = round(kwargs[ATTR_BRIGHTNESS] / 255 * 1000)
            await self._led.set_brightness(fluval_val)
        await self._led.turn_on()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn off LED."""
        await self._led.turn_off()

    async def async_update(self) -> None:
        """Poll device state."""
        try:
            await self._led.read_state()
        except Exception:
            _LOGGER.warning("State poll failed for %s", self._led.ble_device.address)
