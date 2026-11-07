import logging

import pytest
from assertpy import assert_that
from examples.httpbin.__main__ import SECRET_PAYLOAD, scenario_masking
from examples.httpbin.client import HttpbinClient
from pytest_httpx import HTTPXMock


@pytest.mark.parametrize("secret", [SECRET_PAYLOAD["user"]["password"], SECRET_PAYLOAD["items"][0]["token"]])
def test_masking_example_does_not_log_secrets(
    secret: str,
    caplog: pytest.LogCaptureFixture,
    httpx_mock: HTTPXMock,
) -> None:
    response_payload: dict[str, object] = {"json": SECRET_PAYLOAD}
    httpx_mock.add_response(json=response_payload)
    logger = logging.getLogger(__name__)
    caplog.set_level(logging.INFO, logger=logger.name)

    with HttpbinClient("https://masking.test") as client:
        scenario_masking(client, logger)

    assert_that(caplog.text).does_not_contain(secret)
