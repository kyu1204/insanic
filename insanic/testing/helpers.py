import copy
import sys
import ujson as json
import uuid

from enum import Enum
from collections import namedtuple
from setuptools.command.test import test as TestCommand

from insanic.errors import GlobalErrorCodes

User = namedtuple('User', ['id', 'email', 'is_active', 'is_authenticated', 'is_staff'])


class PyTestCommand(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to pytest")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = ""

    def run_tests(self):
        import shlex
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(shlex.split(self.pytest_args))
        sys.exit(errno)

class BaseMockService:

    service_responses = {}
    def _key_for_request(self, method, endpoint):
        return (method.upper(), endpoint)

    async def mock_dispatch(self, method, endpoint, req_ctx={}, *, query_params={}, payload={}, headers={},
                            return_obj=True, propagate_error=False, include_status_code=False, **kwargs):
        key = self._key_for_request(method, endpoint)

        if method == "GET" and endpoint == "/api/v1/user/self":
            return kwargs.get('test_user',
                              User(id=2, email="admin@mymusictaste.com", is_active=True, is_authenticated=True,
                                   is_staff=False))

        if key in self.service_responses:
            if include_status_code:
                return copy.deepcopy(self.service_responses[key][0]), self.service_responses[key][1]
            else:
                return copy.deepcopy(self.service_responses[key][0])

        raise RuntimeError(
            "Unknown service request: {0} {1}. Need to register mock dispatch.".format(method.upper(), endpoint))

    def register_mock_dispatch(self, method, endpoint, response, response_status_code=200):
        key = self._key_for_request(method, endpoint)

        self.service_responses.update({key: (response, response_status_code)})


MockService = BaseMockService()


class DunnoValue:
    def __init__(self, expected_type):
        self.expected_type = expected_type

    def __eq__(self, other):

        if self.expected_type == uuid.UUID and isinstance(other, str):
            try:
                uuid.UUID(other)
            except ValueError:
                return False
            else:
                return True
        else:
            return isinstance(other, self.expected_type)


def test_api_endpoint(insanic_application, authorization_token, endpoint, method, request_headers,
                      request_body, expected_response_status, expected_response_body):

    handler = getattr(insanic_application.test_client, method.lower())

    request_headers.update({"content-type": "application/json", "accept": "application/json"})
    if "Authorization" in request_headers:
        request_headers.update({"Authorization": authorization_token})

    request, response = handler(endpoint,
                                debug=True,
                                headers=request_headers,
                                json=request_body)

    assert expected_response_status == response.status, response.text

    response_body = response.text

    try:
        response_body = json.loads(response.text)
    except ValueError:
        pass

    response_status_category = int(expected_response_status / 100)

    if response_status_category == 2:
        if isinstance(response_body, dict) and isinstance(expected_response_body, dict):
            assert expected_response_body == response_body
        elif isinstance(response_body, dict) and isinstance(expected_response_body, list):
            assert sorted(expected_response_body) == sorted(response_body.keys())
        elif isinstance(response_body, list) and isinstance(expected_response_body, int):
            assert expected_response_body == len(response_body)
        elif isinstance(expected_response_body, str):
            assert expected_response_body == response_body
        else:
            raise RuntimeError("Shouldn't be in here. Check response type.")
    elif response_status_category == 3:
        raise RuntimeError("Shouldn't be in here. Redirects not possible.")
    elif response_status_category == 4:
        # if http status code is in the 4 hundreds, check error code
        if isinstance(expected_response_body, dict):
            assert expected_response_body == response_body, response.text
        elif isinstance(expected_response_body, list):
            assert sorted(expected_response_body) == sorted(response_body.keys()), response.text
        elif isinstance(expected_response_body, Enum):
            assert expected_response_body.value == response_body['error_code']['value'], response.text
        elif isinstance(expected_response_body, int):
            assert expected_response_body == response_body['error_code']['value'], response.text
        else:
            raise RuntimeError("Shouldn't be in here. Check response type.")



TestParams = namedtuple('TestParams', ['method', 'endpoint', 'request_headers', 'request_body',
                                       'expected_response_status', 'expected_response_body'])
def test_parameter_generator(method, endpoint, *, request_headers, request_body, expected_status_code,
                             expected_response, check_authorization=True, check_permissions=True, **kwargs):

    if check_permissions:
        if "permissions_endpoint" not in kwargs:
            raise RuntimeError("'permissions_endpoint' must be passed for permissions check parameters.")

    request_headers.update({"Authorization": ""})

    test_parameters_template = TestParams(method=method, endpoint=endpoint, request_headers=request_headers,
                                          request_body=request_body, expected_response_status=expected_status_code,
                                          expected_response_body=expected_response)
    if check_authorization:
        _req_headers = request_headers.copy()
        if "Authorization" in _req_headers:
            del _req_headers['Authorization']

        p = test_parameters_template._replace(request_headers=_req_headers,
                                              expected_response_status=401,
                                              expected_response_body=GlobalErrorCodes.authentication_credentials_missing)
        # parameters.append(p)
        yield tuple(p)

    if check_permissions:
        p = test_parameters_template._replace(endpoint=kwargs['permissions_endpoint'],
                                              expected_response_status=403,
                                              expected_response_body=GlobalErrorCodes.permission_denied)

        yield tuple(p)

    yield tuple(test_parameters_template)

def test_parameter(method, endpoint, request_headers, request_body, expected_response_status, expected_response_body):
    return [tuple(TestParams(method=method, endpoint=endpoint, request_headers=request_headers,
                             request_body=request_body, expected_response_status=expected_response_status,
                             expected_response_body=expected_response_body))]
