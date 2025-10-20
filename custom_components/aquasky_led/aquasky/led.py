import logging

from bleak import BleakClient
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

_LOGGER = logging.getLogger(__name__)

WRITE_UUID = "00001001-0000-1000-8000-00805f9b34fb"

TURN_ON_LIGHT = "5451744823214a"
TURN_OFF_LIGHT = "5451a29ef5f69d"


class BLELed:
    def __init__(self, ble_device: BLEDevice) -> None:
        self.ble_device = ble_device

    async def turn_on(self):
        await self._send_command(bytes.fromhex(TURN_ON_LIGHT))

    async def turn_off(self):
        await self._send_command(bytes.fromhex(TURN_OFF_LIGHT))

    async def _send_command(self, command: bytes):
        client = await establish_connection(
            BleakClientWithServiceCache,
            self.ble_device,
            self.ble_device.name,
            max_attempts=3,
        )

        _LOGGER.debug("Connected to BLE device %s", self.ble_device.address)

        try:
            await client.write_gatt_char(WRITE_UUID, command, response=False)
            _LOGGER.debug("Sent command %s", command)
        finally:
            await client.disconnect()
