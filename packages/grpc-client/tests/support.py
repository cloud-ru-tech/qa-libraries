from typing import cast

import grpc


def code_number(status_code: grpc.StatusCode) -> int:
    """Get the numeric value of a gRPC status code.

    :param status_code: status code
    :return: numeric code value as sent over the network
    """
    return cast("tuple[int, str]", status_code.value)[0]
