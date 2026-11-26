import pytest
from assertpy import assert_that


def test_websocket_explains_how_to_install_missing_dependency(pytester: pytest.Pytester) -> None:
    script = pytester.makepyfile(
        r"""
        import sys

        sys.modules["wsproto"] = None

        import pytest
        from http_client import HttpClient

        with HttpClient("http://localhost") as client:
            with pytest.raises(ImportError, match=r"cloudru-qa-http-client\[ws\]"):
                with client.websocket("/chat"):
                    pytest.fail("WebSocket opened without the optional dependency")
        """,
    )
    result = pytester.runpython(script)

    assert_that(result.ret, result.stderr.str()).is_equal_to(0)
