from dataclasses import dataclass

import grpc

from .metadata import merge_metadata
from .types import MetadataType


class _UseClientDefault:
    """Marker for a call option whose value comes from client settings.

    Distinguish an unset option from an explicitly supplied `None`:
    `timeout=None` means a call without a timeout.
    """

    def __repr__(self) -> str:
        """Return the string representation of metadata."""
        return "USE_CLIENT_DEFAULT"

    def __bool__(self) -> bool:
        return False


USE_CLIENT_DEFAULT = _UseClientDefault()


@dataclass(frozen=True, slots=True, kw_only=True)
class CallOptions:
    """Options for a single gRPC call.

    Unspecified options come from client settings.
    """

    # Call timeout in seconds. `None` means no timeout.
    timeout: float | _UseClientDefault | None = USE_CLIENT_DEFAULT

    # Request metadata added to client metadata.
    metadata: MetadataType | None = None

    # Credentials for this call.
    credentials: grpc.CallCredentials | None = None

    # Wait for the channel to become ready instead of immediately failing with UNAVAILABLE.
    wait_for_ready: bool | None = None

    # Call message compression algorithm.
    compression: grpc.Compression | None = None

    def merge(self, other: "CallOptions") -> "CallOptions":
        """Overlay call options on the current options.

        Metadata is merged; other explicitly set `other` options override current values.

        :param other: higher-priority options
        :return: merged options
        """
        return CallOptions(
            timeout=self.timeout if isinstance(other.timeout, _UseClientDefault) else other.timeout,
            metadata=merge_metadata(self.metadata, other.metadata),
            credentials=other.credentials if other.credentials is not None else self.credentials,
            wait_for_ready=other.wait_for_ready if other.wait_for_ready is not None else self.wait_for_ready,
            compression=other.compression if other.compression is not None else self.compression,
        )

    def resolve_timeout(self, default: float | None) -> float | None:
        """Calculate the effective call timeout.

        :param default: client-provided value
        :return: timeout in seconds, or None if unlimited
        """
        return default if isinstance(self.timeout, _UseClientDefault) else self.timeout
