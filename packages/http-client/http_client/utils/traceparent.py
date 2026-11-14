import binascii
import os

TRACEPARENT_VERSION = "00"
TRACEPARENT_FLAGS = "01"


def generate() -> str:
    """Generate traceparent."""
    trace_id = binascii.hexlify(os.urandom(16)).decode()
    random_id = binascii.hexlify(os.urandom(8)).decode()
    return f"{TRACEPARENT_VERSION}-{trace_id}-{random_id}-{TRACEPARENT_FLAGS}"
