import aiohttp
import traceback
import ujson as json

from types import SimpleNamespace

from aws_xray_sdk.core import xray_recorder
from aws_xray_sdk.core.models import http
from aws_xray_sdk.ext.util import inject_trace_header, strip_url

from insanic import status
from insanic.tracing.utils import get_safe_dict
from insanic.utils import try_json_decode

# All aiohttp calls will entail outgoing HTTP requests, only in some ad-hoc
# exceptions the namespace will be flip back to local.
REMOTE_NAMESPACE = 'remote'
LOCAL_NAMESPACE = 'local'
LOCAL_EXCEPTIONS = (
    aiohttp.client_exceptions.ClientConnectionError,
    # DNS issues
    OSError
)


async def begin_subsegment(session, trace_config_ctx, params):
    name = trace_config_ctx.name if trace_config_ctx.name else strip_url(str(params.url))
    subsegment = xray_recorder.begin_subsegment(name, REMOTE_NAMESPACE)

    # No-op if subsegment is `None` due to `LOG_ERROR`.
    if not subsegment:
        trace_config_ctx.give_up = True
    else:
        trace_config_ctx.give_up = False
        subsegment.put_http_meta(http.METHOD, params.method)
        subsegment.put_http_meta(http.URL, params.url.human_repr())
        inject_trace_header(params.headers, subsegment)


async def end_subsegment(session, trace_config_ctx, params):
    if trace_config_ctx.give_up:
        return

    subsegment = xray_recorder.current_subsegment()
    subsegment.put_http_meta(http.STATUS, params.response.status)

    if params.response.status >= status.HTTP_400_BAD_REQUEST:
        resp = await params.response.text()
        resp = try_json_decode(resp)
        resp = get_safe_dict(resp)
        subsegment.put_annotation('response', json.dumps(resp))

    xray_recorder.end_subsegment()


async def end_subsegment_with_exception(session, trace_config_ctx, params):
    if trace_config_ctx.give_up:
        return

    subsegment = xray_recorder.current_subsegment()
    subsegment.add_exception(
        params.exception,
        traceback.extract_stack(limit=xray_recorder._max_trace_back)
    )

    if isinstance(params.exception, LOCAL_EXCEPTIONS):
        subsegment.namespace = LOCAL_NAMESPACE

    xray_recorder.end_subsegment()


def aws_xray_trace_config(name=None):
    """
    :param name: name used to identify the subsegment, with None internally the URL will
                 be used as identifier.
    :returns: TraceConfig.
    """

    def _trace_config_ctx_factory(trace_request_ctx):
        return SimpleNamespace(
            name=trace_request_ctx.get('name', None),
            trace_request_ctx=trace_request_ctx
        )

    trace_config = aiohttp.TraceConfig(trace_config_ctx_factory=_trace_config_ctx_factory)
    trace_config.on_request_start.append(begin_subsegment)
    trace_config.on_request_end.append(end_subsegment)
    trace_config.on_request_exception.append(end_subsegment_with_exception)
    return trace_config
