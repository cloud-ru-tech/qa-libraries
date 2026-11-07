import secrets

# Версия формата traceparent, единственная описанная в W3C Trace Context.
TRACEPARENT_VERSION = "00"

# Флаг «трасса записывается».
FLAGS_SAMPLED = "01"

# Флаг «решение о записи трассы не принято».
FLAGS_NOT_SAMPLED = "00"

_TRACE_ID_BYTES = 16
_SPAN_ID_BYTES = 8


def generate(flags: str = FLAGS_SAMPLED) -> str:
    """Сгенерировать значение заголовка traceparent.

    :param flags: флаги трассировки, по умолчанию «трасса записывается»
    :return: traceparent в формате W3C Trace Context
    """
    return f"{TRACEPARENT_VERSION}-{_random_id(_TRACE_ID_BYTES)}-{_random_id(_SPAN_ID_BYTES)}-{flags}"


def _random_id(size: int) -> str:
    """Сгенерировать идентификатор трассировки заданной длины.

    Спецификация W3C запрещает идентификаторы из одних нулей, поэтому такое значение перегенерируется.

    :param size: длина идентификатора в байтах
    :return: идентификатор в виде hex-строки нижнего регистра
    """
    while True:
        value = secrets.token_hex(size)
        if value.strip("0"):
            return value
