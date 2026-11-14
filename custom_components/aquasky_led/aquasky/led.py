import asyncio
import logging
import os

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

_LOGGER = logging.getLogger(__name__)

WRITE_UUID = "00001001-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "00001002-0000-1000-8000-00805f9b34fb"

_CHANNEL_COUNT = 4
_BRIGHTNESS_MAX = 1000
_STATE_TIMEOUT = 2.0  # seconds to wait for a state notification response


# ---------------------------------------------------------------------------
# Protocol helpers — pure functions, no HA dependency
# ---------------------------------------------------------------------------

def encode_message(raw: bytes) -> bytes:
    """Encode a raw protocol frame for BLE transmission.

    Wire format: 54 [(len+1)^54] [K^54] [b0^K] ... [b(n-1)^K]
    K is a fresh random byte each call; the receiver recovers it via pkt[0]^pkt[2].
    """
    k = os.urandom(1)[0]
    out = bytearray(len(raw) + 3)
    out[0] = 0x54
    out[1] = (len(raw) + 1) ^ 0x54
    out[2] = k ^ 0x54
    for i, b in enumerate(raw):
        out[3 + i] = b ^ k
    return bytes(out)


def decode_message(pkt: bytes) -> bytes:
    """Decode a received BLE packet back to the raw protocol frame."""
    if len(pkt) < 3:
        return b""
    k = pkt[0] ^ pkt[2]
    return bytes(b ^ k for b in pkt[3:])


def _crc(data: bytes) -> int:
    c = 0
    for b in data:
        c ^= b
    return c


def _build_set_channels(values: list[int]) -> bytes:
    """Build a CMD 0x04 (set brightness) frame. Values are 0–1000 per channel."""
    raw = bytearray([0x68, 0x04])
    for v in values:
        raw += bytes([(v >> 8) & 0xFF, v & 0xFF])
    raw.append(_crc(raw))
    return bytes(raw)


# ---------------------------------------------------------------------------
# BLE device wrapper
# ---------------------------------------------------------------------------

class BLELed:
    def __init__(self, ble_device: BLEDevice) -> None:
        self.ble_device = ble_device
        self._lock = asyncio.Lock()
        self._client: BleakClientWithServiceCache | None = None
        self._notify_buf = bytearray()
        self._state_event = asyncio.Event()
        self.is_on: bool | None = None
        self._brightness: int = _BRIGHTNESS_MAX  # 0–1000

    @property
    def brightness_pct(self) -> float | None:
        """Brightness as 0.0–1.0, or None if state not yet known."""
        if self.is_on is None:
            return None
        return self._brightness / _BRIGHTNESS_MAX

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def turn_on(self) -> None:
        await self._send(encode_message(bytes([0x68, 0x03, 0x01, 0x6A])))
        self.is_on = True

    async def turn_off(self) -> None:
        await self._send(encode_message(bytes([0x68, 0x03, 0x00, 0x6B])))
        self.is_on = False

    async def set_brightness(self, value_0_to_1000: int) -> None:
        """Set all channels to the same brightness (0–1000)."""
        v = max(0, min(_BRIGHTNESS_MAX, value_0_to_1000))
        await self._send(encode_message(_build_set_channels([v] * _CHANNEL_COUNT)))
        self._brightness = v

    async def read_state(self) -> None:
        """Request device state; waits for the notification response."""
        async with self._lock:
            self._notify_buf.clear()
            self._state_event.clear()
            client = await self._ensure_connected()
            await client.write_gatt_char(
                WRITE_UUID,
                encode_message(bytes([0x68, 0x05, 0x6D])),
                response=False,
            )

        try:
            await asyncio.wait_for(self._state_event.wait(), timeout=_STATE_TIMEOUT)
        except asyncio.TimeoutError:
            _LOGGER.warning("Timed out waiting for state from %s", self.ble_device.address)

    async def disconnect(self) -> None:
        """Close the BLE connection (called on integration unload)."""
        if self._client and self._client.is_connected:
            await self._client.disconnect()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        """Return the connected client, reconnecting if the connection dropped."""
        if self._client is not None and self._client.is_connected:
            return self._client

        _LOGGER.debug("Connecting to %s", self.ble_device.address)
        self._client = await establish_connection(
            BleakClientWithServiceCache,
            self.ble_device,
            self.ble_device.name,
            disconnected_callback=self._on_disconnect,
            max_attempts=3,
        )
        await self._client.start_notify(NOTIFY_UUID, self._on_notify)
        _LOGGER.debug("Connected to %s", self.ble_device.address)
        return self._client

    def _on_disconnect(self, _client: BleakClientWithServiceCache) -> None:
        """Called by bleak when the connection drops unexpectedly."""
        _LOGGER.debug("Disconnected from %s — will reconnect on next operation", self.ble_device.address)
        self._client = None

    def _on_notify(self, _: BleakGATTCharacteristic, data: bytearray) -> None:
        """Accumulate notification fragments and parse state when complete."""
        self._notify_buf.extend(decode_message(bytes(data)))
        expected = _CHANNEL_COUNT * 6 + 6
        raw = bytes(self._notify_buf)
        if len(raw) >= expected and raw[0] == 0x68 and raw[1] == 0x05 and raw[2] == 0x00:
            self._parse_state(raw)
            self._notify_buf.clear()
            self._state_event.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _send(self, command: bytes) -> None:
        async with self._lock:
            client = await self._ensure_connected()
            await client.write_gatt_char(WRITE_UUID, command, response=False)

    def _parse_state(self, raw: bytes) -> None:
        self.is_on = bool(raw[3] & 1)
        channels = [
            raw[5 + i * 2] | (raw[6 + i * 2] << 8)
            for i in range(_CHANNEL_COUNT)
        ]
        self._brightness = max(channels) if channels else 0
        _LOGGER.debug(
            "State: on=%s brightness=%s channels=%s",
            self.is_on, self._brightness, channels,
        )
