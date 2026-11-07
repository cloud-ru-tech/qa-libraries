"""Connection and session errors."""


class SessionNotInititalizedError(Exception):
    """Report an operation without an initialized session."""

    def __init__(self, message: str = "Session not initialized") -> None:
        """Keep the session failure reason.

        :param message: Human-readable failure reason.
        """
        self.message = message
        super().__init__(message)


class StreamInitFailureError(Exception):
    """Report a transport which failed to provide streams."""

    def __init__(self, message: str = "Failed to establish streams") -> None:
        """Keep the transport failure reason.

        :param message: Human-readable failure reason.
        """
        self.message = message
        super().__init__(message)
