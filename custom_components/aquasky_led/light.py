"""Light entity for the Fluval Aquasky Bluetooth LED integration."""

from homeassistant.components import bluetooth
from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_MAC
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .aquasky.led import BLELed


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

    def __init__(self, led: BLELed) -> None:
        """Initialise entity."""
        self._attr_name = led.ble_device.name
        self._attr_unique_id = led.ble_device.address
        self._led = led

    @property
    def supported_color_modes(self):
        return {ColorMode.ONOFF}

    @property
    def color_mode(self):
        return ColorMode.ONOFF

    async def async_turn_on(self, **kwargs):
        """Turn on LED."""
        await self._led.turn_on()

    async def async_turn_off(self, **kwargs):
        """Turn off LED."""
        await self._led.turn_off()
