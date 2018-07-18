import pytest
from insanic import status
from insanic.responses import json_response


@pytest.mark.parametrize('headers', (
        {},
        {"Content-Length": 4}
))
def test_malformed_204_response_has_no_content_length(headers):
    # flask-restful can generate a malformed response when doing `return '', 204`

    response = json_response({}, status=status.HTTP_204_NO_CONTENT, headers=headers)
    assert response.status == status.HTTP_204_NO_CONTENT
    assert response.body == b""

    http_response = response.output().split(b'\r\n')

    assert bytes(status.HTTP_204_NO_CONTENT) in http_response[0]
    assert b"No Content" in http_response[0]
    assert b"Content-Type" not in http_response[2]
