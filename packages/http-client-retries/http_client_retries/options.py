from typing import cast

from http_client import AsyncHttpClient, BaseHttpClient, ClientOption
from http_client import options as http_options

from .config import NO_OVERRIDES, RetryOverrides
from .decorators import async_stream_decorator, send_decorator, stream_decorator
from .policy import ResponseCondition, RetryPolicy

# Store the policy on the client: both options update one instance so the request
# uses one retry loop with a shared attempt budget.
_POLICY_ATTR = "_http_client_retries_policy"


def with_retries_failed_requests(
    *,
    overrides: RetryOverrides = NO_OVERRIDES,
) -> ClientOption:
    """Option for retrying requests on server connection errors.

    Apply to both regular and streaming requests.

    Read default ``overrides`` fields from the global configuration at request time,
    so a later `configure()` call still takes effect. Supplied values override it
    only for this client; ``RetryOverrides(before_sleep_hook=None)`` disables the global hook.

    :param overrides: Global policy overrides for this client.
    :return: Client configuration option.
    """

    def option(client: BaseHttpClient) -> None:
        policy = _policy_of(client)
        policy.retry_on_network_errors = True
        policy.overrides = policy.overrides.merge(overrides)

    return option


def with_retries_if(
    retry_condition: ResponseCondition,
    *,
    overrides: RetryOverrides = NO_OVERRIDES,
) -> ClientOption:
    """Option for retrying requests when retry_condition is met.

    Apply to both regular and streaming requests. For streams, check the condition
    immediately after opening the stream, while the response body is still unread.

    Policy override rules match :func:`with_retries_failed_requests`.
    When combined with other retry options, all conditions run
    in one loop with a shared attempt budget.

    :param retry_condition: Condition that marks a response for retry.
    :param overrides: Global policy overrides for this client.
    :return: Client configuration option.
    """

    def option(client: BaseHttpClient) -> None:
        policy = _policy_of(client)
        policy.conditions.append(retry_condition)
        policy.overrides = policy.overrides.merge(overrides)

    return option


def _policy_of(client: BaseHttpClient) -> RetryPolicy:
    """Return the client policy, creating it and attaching decorators on first access."""
    policy = cast("RetryPolicy | None", getattr(client, _POLICY_ATTR, None))
    if policy is not None:
        return policy

    policy = RetryPolicy()
    setattr(client, _POLICY_ATTR, policy)

    # Register decorators once and read the policy at request time,
    # so conditions added by subsequent options are also considered.
    http_options.with_send_decorator(send_decorator(policy))(client)

    build_stream_decorator = async_stream_decorator if isinstance(client, AsyncHttpClient) else stream_decorator
    http_options.with_stream_decorator(build_stream_decorator(policy))(client)

    return policy
