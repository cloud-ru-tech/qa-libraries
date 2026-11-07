from typing import cast

import grpc


def code_number(status_code: grpc.StatusCode) -> int:
    """Получить числовое значение кода статуса gRPC.

    :param status_code: код статуса
    :return: числовое значение кода, как его передают по сети
    """
    return cast("tuple[int, str]", status_code.value)[0]
