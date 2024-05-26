"""The Nokia WIFI integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant

from .router import NokiaWifiRouter

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]

type NokiaWifiConfigEntry = ConfigEntry[NokiaWifiRouter]


async def async_setup_entry(hass: HomeAssistant, entry: NokiaWifiConfigEntry) -> bool:
    """Set up Nokia WIFI from a config entry."""

    router = NokiaWifiRouter(hass, entry)
    await router.setup()

    async def async_close_connection(event: Event) -> None:
        """Close router connection on HA Stop."""
        await router.close()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    entry.runtime_data = router

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: NokiaWifiConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        router = entry.runtime_data
        await router.close()

    return unload_ok
