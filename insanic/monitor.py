import asyncio
import time

from sanic import Blueprint
from sanic.response import json, text

from insanic import __version__
from insanic.conf import settings
from insanic.exceptions import APIException
from insanic.loading import get_service
from insanic.status import HTTP_200_OK

blueprint_monitor = Blueprint('monitor', strict_slashes=True)


# A service has an health check API endpoint (e.g. HTTP /health) that returns the health of the service.
# The API endpoint handler performs various checks, such as
#
# the status of the connections to the infrastructure services used by the service instance
# the status of the host, e.g. disk space
# application specific logic

async def response_time(func, *args, **kwargs):
    start = time.time()
    try:
        response, status_code = await func(*args, **kwargs)
    except APIException as e:
        return {"response": e.__dict__(), "status_code": e.status_code,
                "request_time": f"{int((time.time()-start) * 1000)} ms"}
    else:
        return {"response": response, "status_code": status_code,
                "request_time": f"{int((time.time()-start) * 1000)} ms"}


@blueprint_monitor.route('/ping/')
async def ping(request):
    try:
        depth = int(request.query_params.get("depth", 0))
    except ValueError:
        depth = 0

    if depth and len(settings.SERVICE_CONNECTIONS) > 0:
        ping_tasks = {}
        ping_responses = {}
        for s in settings.SERVICE_CONNECTIONS:
            try:
                service = get_service(s)
            except RuntimeError as e:
                ping_responses.update({s: {"error": e.args[0]}})
            else:
                ping_tasks.update({s: asyncio.ensure_future(
                    response_time(service.http_dispatch, 'GET', f"/{s}/ping/",
                                  query_params={"depth": depth - 1},
                                  include_status_code=True)
                )})

        await asyncio.gather(*ping_tasks.values())

        for k, v in ping_tasks.items():
            ping_responses.update({k: v.result()})

        return json(ping_responses)

    else:
        return text("pong")


@blueprint_monitor.route('/health/')
def health_check(request):
    return json({
        "service": settings.SERVICE_NAME,
        "service_version": settings.SERVICE_VERSION,
        "status": "OK",
        "insanic_version": __version__,
    }, status=HTTP_200_OK)
