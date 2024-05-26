"""HTTP API for Nokia WiFi routers."""

from collections import namedtuple
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

Device = namedtuple("Device", ["ip", "name", "connected_to"])


class AuthFailure(Exception):
    """Exception raised when auth failed."""


class HttpApi:
    """Use admin http API to communicate with the router."""

    def __init__(self, hass: HomeAssistant, host: str, password: str) -> None:
        """Initialize a Nokia WiFi API."""
        self.hass = hass

        self.host = host
        self._password = password

        self.__sid = None
        self.__lsid = None

    async def async_login(self):
        """Login to the router."""
        session = async_get_clientsession(self.hass)
        url = f"https://{self.host}/login_app.cgi"
        data = {"name": "admin", "pswd": self._password, "srip": ""}
        async with session.post(url, timeout=10, data=data, verify_ssl=False) as res:
            res.raise_for_status()

            data = await res.json(content_type=None)
            self.__sid = data["cookie"]["sid"]
            self.__lsid = data["cookie"]["lsid"]

    async def async_get_devices(self, tries=1) -> list[Device]:
        """Get devices connected to the router."""

        if tries > 3:
            raise AuthFailure("async_get_devices auth failed more than 3 time")

        if self.__sid is None or self.__lsid is None:
            await self.async_login()

        session = async_get_clientsession(self.hass)
        url = f"https://{self.host}/index_app.cgi"
        headers = {"Cookie": f"{self.__sid}; {self.__lsid}"}
        async with session.get(
            url, timeout=30, headers=headers, verify_ssl=False
        ) as res:
            if res.status == 403:
                _LOGGER.warning("Auth failed, trying to login again")
                await self.async_login()
                return await self.async_get_devices(tries + 1)

            res.raise_for_status()

            data = await res.json(content_type=None)
            return {
                item["MACAddress"]: Device(
                    item["IPAddress"],
                    item["HostName"],
                    item["InterfaceType"],
                )
                for item in data["devices_list"]
            }
