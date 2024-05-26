"""Support for Nokia WiFi routers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging

from homeassistant.components.device_tracker import (
    DEFAULT_CONSIDER_HOME,
    DOMAIN as TRACKER_DOMAIN,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo, format_mac
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import Device, HttpApi
from .const import DOMAIN

SCAN_INTERVAL = timedelta(seconds=60)
_LOGGER = logging.getLogger(__name__)


class NokiaWifiDeviceInfo:
    """Nokia WiFi device info."""

    def __init__(self, mac: str, name: str | None = None) -> None:
        """Initialize a AsusWrt device info."""
        self._mac = mac
        self._name = name
        self._ip_address: str | None = None
        self._last_activity: datetime | None = None
        self._connected = False

    def update(self, dev_info: Device | None = None, consider_home: int = 0) -> None:
        """Update device info."""
        utc_point_in_time = dt_util.utcnow()
        if dev_info:
            if not self._name:
                self._name = dev_info.name or self._mac.replace(":", "_")
            self._ip_address = dev_info.ip
            self._last_activity = utc_point_in_time
            self._connected = True

        elif self._connected:
            self._connected = (
                self._last_activity is not None
                and (utc_point_in_time - self._last_activity).total_seconds()
                < consider_home
            )
            self._ip_address = None

    @property
    def is_connected(self) -> bool:
        """Return connected status."""
        return self._connected

    @property
    def mac(self) -> str:
        """Return device mac address."""
        return self._mac

    @property
    def name(self) -> str | None:
        """Return device name."""
        return self._name

    @property
    def ip_address(self) -> str | None:
        """Return device ip address."""
        return self._ip_address

    @property
    def last_activity(self) -> datetime | None:
        """Return device last activity."""
        return self._last_activity


class NokiaWifiRouter:
    """Nokia WiFi Router class."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize a Nokia WiFi router."""
        self.hass = hass
        self._entry = entry

        self._devices: dict[str, NokiaWifiDeviceInfo] = {}
        self._connected_devices: int = 0
        self._connect_error: bool = False

        self._on_close: list[Callable] = []

        self._api = HttpApi(self.hass, entry.data[CONF_HOST], entry.data[CONF_PASSWORD])

    async def setup(self) -> None:
        """Set up the Nokia WiFi router."""

        # Load tracked entities from registry
        entity_reg = er.async_get(self.hass)
        track_entries = er.async_entries_for_config_entry(
            entity_reg, self._entry.entry_id
        )

        for entry in track_entries:
            if entry.domain != TRACKER_DOMAIN:
                continue
            device_mac = format_mac(entry.unique_id)

            self._devices[device_mac] = NokiaWifiDeviceInfo(
                device_mac, entry.original_name
            )

        await self.update_devices()

        self.async_on_close(
            async_track_time_interval(self.hass, self.update_all, SCAN_INTERVAL)
        )

    async def update_all(self, now: datetime | None = None) -> None:
        """Update all AsusWrt platforms."""
        await self.update_devices()

    async def update_devices(self) -> None:
        """Update devices tracker."""

        new_device = False
        _LOGGER.debug("Checking devices for Nokia Wifi router %s", self.host)
        try:
            devices = await self._api.async_get_devices()
        except OSError as exc:
            if not self._connect_error:
                self._connect_error = True
                _LOGGER.error(
                    "Error connecting to Nokia Wifi router %s for device update: %s",
                    self.host,
                    exc,
                )
            return

        if self._connect_error:
            self._connect_error = False
            _LOGGER.info("Reconnected to Nokia Wifi router %s", self.host)

        self._connected_devices = len(devices)
        # consider_home: int = self._options.get(
        #     CONF_CONSIDER_HOME, DEFAULT_CONSIDER_HOME.total_seconds()
        # )
        consider_home = DEFAULT_CONSIDER_HOME.total_seconds()
        # track_unknown: bool = self._options.get(
        #     CONF_TRACK_UNKNOWN, DEFAULT_TRACK_UNKNOWN
        # )
        track_unknown = True

        for device_mac, device in self._devices.items():
            dev_info = devices.pop(device_mac, None)
            device.update(dev_info, consider_home)

        for device_mac, dev_info in devices.items():
            if not track_unknown and not dev_info.name:
                continue
            new_device = True
            device = NokiaWifiDeviceInfo(device_mac)
            device.update(dev_info)
            self._devices[device_mac] = device

        async_dispatcher_send(self.hass, self.signal_device_update)
        if new_device:
            async_dispatcher_send(self.hass, self.signal_device_new)

    async def close(self) -> None:
        """Close the connection."""
        for func in self._on_close:
            func()
        self._on_close.clear()

    @callback
    def async_on_close(self, func: CALLBACK_TYPE) -> None:
        """Add a function to call when router is closed."""
        self._on_close.append(func)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        # TODO we can get more info from the api
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.unique_id or "NokiaWifi")},
            name=self.host,
            model="Nokia Wifi",
            manufacturer="Nokia",
            configuration_url=f"https://{self.host}",
        )

    @property
    def signal_device_new(self) -> str:
        """Event specific per NokiaWifi entry to signal new device."""
        return f"{DOMAIN}-device-new"

    @property
    def signal_device_update(self) -> str:
        """Event specific per NokiaWifi entry to signal updates in devices."""
        return f"{DOMAIN}-device-update"

    @property
    def host(self) -> str:
        """Return router hostname."""
        return self._api.host

    @property
    def unique_id(self) -> str:
        """Return router unique id."""
        return self._entry.unique_id or self._entry.entry_id

    @property
    def devices(self) -> dict[str, NokiaWifiDeviceInfo]:
        """Return devices."""
        return self._devices
