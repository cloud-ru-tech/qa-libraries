import secrets

# Traceparent format version, the only version defined by W3C Trace Context.
TRACEPARENT_VERSION = "00"

# Flag indicating that the trace is recorded.
FLAGS_SAMPLED = "01"

# Flag indicating that the trace recording decision has not been made.
FLAGS_NOT_SAMPLED = "00"

_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8


def generate(flags: str = FLAGS_SAMPLED) -> str:
    """Generate a traceparent header value.

    :param flags: trace flags, defaults to recording the trace
    :return: traceparent in W3C Trace Context format
    """
    return f"{TRACEPARENT_VERSION}-{_random_id(_TRACE_ID_BYTES)}-{_random_id(_SPAN_ID_BYTES)}-{flags}"


def _random_id(size: int) -> str:
    """Generate a trace identifier of the specified length.

    W3C forbids all-zero identifiers, so regenerate such values.

    :param size: identifier length in bytes
    :return: identifier as a lowercase hex string
    """
    while True:
        value = secrets.token_hex(size)
        if value.strip("0"):
            return value
