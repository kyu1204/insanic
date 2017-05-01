import aiohttp
import ujson as json

from asyncio import get_event_loop
from sanic.constants import HTTP_METHODS
from urllib.parse import urlunsplit, urljoin

from insanic.conf import settings
from insanic.errors import GlobalErrorCodes
from insanic.exceptions import ServiceUnavailable503Error
from insanic.utils import to_object

class Service:

    def __init__(self, service_type):

        self._service_type = service_type
        self._session = None
        self._url_scheme = settings.API_GATEWAY_SCHEME
        if service_type not in settings.SERVICES.keys():
            raise AssertionError("Invalid service type.")
        if settings.MMT_ENV == "local":
            api_host = settings.API_GATEWAY_HOST
        else:
            api_host = "mmt-server-{0}".format(service_type)

        self._url_netloc = "{0}:{1}".format(api_host, settings.SERVICES[service_type].get('externalserviceport'))
        self._url_partial_path = "/api/v1/{0}".format(service_type)
        self._base_url = urlunsplit((self._url_scheme, self._url_netloc, self._url_partial_path, "", ""))
        self.remove_headers = ["content-length", 'user-agent', 'host', 'postman-token']

        print(settings)
        print(self._url_netloc)

    @property
    def session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(loop=get_event_loop(), connector=aiohttp.TCPConnector(limit_per_host=10))
        return self._session

    def _construct_url(self, endpoint):
        return urljoin(self._base_url, endpoint)


    async def http_dispatch(self, method, endpoint, payload={}, headers={}):

        if method.upper() not in HTTP_METHODS:
            raise ValueError("{0} is not a valid method.".format(method))

        return await self._dispatch(method, endpoint, payload, headers)

    def _prepare_headers(self, headers):
        for h in self.remove_headers:
            if h in headers:
                del headers[h]

        headers.update({"accept": "application/json"})
        return headers


    async def _dispatch(self, method, endpoint, payload={}, headers={}):
        request_method = getattr(self.session, method.lower(), None)
        url = self._construct_url(endpoint)
        headers = self._prepare_headers(headers)
        try:
            async with request_method(url, headers=headers) as resp:
                assert resp.status == 200
                response = await resp.json()
        except aiohttp.client_exceptions.ClientConnectionError:
            if settings.MMT_ENV == "production":
                msg = "Service unavailable. Please try again later."
            else:
                msg = "Cannot connect to {0}. Please try again later".format(self._service_type)
                print(msg)
                raise
            raise ServiceUnavailable503Error(msg, GlobalErrorCodes.service_unavailable)

        return to_object(response)
