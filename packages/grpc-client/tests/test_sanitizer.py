from uuid import uuid4

from grpc_client.utils.sanitizer import (
    DEFAULT_SANITIZE_KEYS,
    DEPTH_EXCEEDED,
    MASK,
    MAX_DEPTH,
    sanitize,
    sanitize_metadata,
)

from .assertions import assert_that


def test_masks_top_level_field() -> None:
    """Поле верхнего уровня маскируется по имени."""
    result = sanitize({"login": "kettle", "password": "hot-water"}, ["password"])

    assert_that(result["password"]).is_equal_to(MASK)


def test_keeps_other_fields_intact() -> None:
    """Поля, не указанные в списке, остаются нетронутыми."""
    result = sanitize({"login": "kettle", "password": "hot-water"}, ["password"])

    assert_that(result["login"]).is_equal_to("kettle")


def test_masks_nested_field_by_path() -> None:
    """Вложенное поле маскируется по glom-пути."""
    result = sanitize({"account": {"secret": "moonlight"}}, ["account.secret"])

    assert_that(result["account"]["secret"]).is_equal_to(MASK)


def test_masks_field_in_every_list_item() -> None:
    """Поле маскируется в каждом элементе списка."""
    result = sanitize({"keys": [{"value": "one"}, {"value": "two"}]}, ["keys.*.value"])

    assert_that([item["value"] for item in result["keys"]]).contains_only(MASK)


def test_keeps_source_unchanged() -> None:
    """Исходная структура не изменяется."""
    source = {"token": "original-value"}

    sanitize(source, ["token"])

    assert_that(source["token"]).is_equal_to("original-value")


def test_returns_copy_when_no_keys_given() -> None:
    """Без ключей маскирования возвращается копия, а не сама структура."""
    source = {"any": "value"}

    assert_that(sanitize(source, [])).is_not_same_as(source)


def test_masks_metadata_value_by_key() -> None:
    """Значение метаданных маскируется по имени ключа."""
    result = sanitize_metadata({"authorization": "Bearer abc"}, ["authorization"])

    assert_that(dict(result)["authorization"]).is_equal_to(MASK)


def test_masks_metadata_key_ignoring_case() -> None:
    """Имя ключа метаданных сопоставляется без учета регистра."""
    result = sanitize_metadata({"Authorization": "Bearer abc"}, ["authorization"])

    assert_that(dict(result)["Authorization"]).is_equal_to(MASK)


def test_masks_metadata_key_containing_dot() -> None:
    """Ключ метаданных с точкой маскируется целиком, а не разбирается как путь.

    Спецификация gRPC разрешает точку в именах ключей, поэтому имя нельзя трактовать как glom-путь.
    """
    result = sanitize_metadata({"x.secret-token": "value-to-hide"}, ["x.secret-token"])

    assert_that(dict(result)["x.secret-token"]).is_equal_to(MASK)


def test_keeps_metadata_without_sensitive_keys() -> None:
    """Метаданные без конфиденциальных ключей остаются как есть."""
    result = sanitize_metadata({"x-request-id": "req-17"}, ["authorization"])

    assert_that(dict(result)["x-request-id"]).is_equal_to("req-17")


def test_keeps_repeated_metadata_keys_after_masking() -> None:
    """Маскирование сохраняет все повторяющиеся ключи."""
    result = sanitize_metadata([("x-key", "first"), ("x-key", "second")], ["x-key"])

    assert_that(result).is_length(2)


def test_masks_every_value_of_repeated_metadata_key() -> None:
    """Маскируется каждое значение повторяющегося ключа, а не только первое."""
    result = sanitize_metadata([("x-key", "first"), ("x-key", "second")], ["x-key"])

    assert_that([value for _, value in result]).contains_only(MASK)


def test_keeps_field_with_shifted_word_boundary() -> None:
    """Поле с другой границей слов не считается секретом.

    protobuf сериализует `sec_ret` как `secRet`: без учета границ оно совпало бы с `secret`.
    """
    result = sanitize({"secRet": "не секрет"}, ["secret"])

    assert_that(result["secRet"]).is_equal_to("не секрет")


def test_masks_deeply_nested_payload_without_error() -> None:
    """Предельно вложенное сообщение не роняет подготовку лога."""
    payload: dict[str, object] = {}
    current = payload
    for _ in range(2000):
        nested: dict[str, object] = {}
        current["nested"] = nested
        current = nested

    assert_that(sanitize(payload, list(DEFAULT_SANITIZE_KEYS))).is_not_none()


def test_masks_nested_field_by_plain_name() -> None:
    """Имя поля без разделителей маскирует значение на любом уровне вложенности."""
    result = sanitize({"user": {"password": "kitchen-key"}}, ["password"])

    assert_that(result["user"]["password"]).is_equal_to(MASK)


def test_masks_typical_secret_inside_nested_payload() -> None:
    """Типовые ключи маскируются во вложенном теле сообщения без дополнительной настройки."""
    result = sanitize({"credentials": {"token": "field-secret"}}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["credentials"]["token"]).is_equal_to(MASK)


def test_masks_field_by_name_inside_list() -> None:
    """Имя поля маскирует значение и внутри списков."""
    result = sanitize({"items": [{"secret": "one"}, {"secret": "two"}]}, ["secret"])

    assert_that([item["secret"] for item in result["items"]]).contains_only(MASK)


def test_keeps_non_secret_fields_of_nested_payload() -> None:
    """Соседние поля вложенного объекта остаются нетронутыми."""
    result = sanitize({"user": {"password": "hidden", "login": "visible"}}, ["password"])

    assert_that(result["user"]["login"]).is_equal_to("visible")


def test_masks_protobuf_camel_case_field() -> None:
    """Имя в snake_case маскирует поле, которое protobuf сериализовал в camelCase."""
    result = sanitize({"accessToken": "camel-secret"}, ["access_token"])

    assert_that(result["accessToken"]).is_equal_to(MASK)


def test_masks_typical_camel_case_secret_by_default() -> None:
    """Типовые секреты маскируются в том виде, в каком их отдает protobuf."""
    result = sanitize({"user": {"refreshToken": "renew-me"}}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["user"]["refreshToken"]).is_equal_to(MASK)


def test_keeps_field_with_similar_name() -> None:
    """Поле с похожим, но другим именем остается нетронутым."""
    result = sanitize({"accessCount": 42}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["accessCount"]).is_equal_to(42)


def test_masks_subtree_beyond_depth_limit() -> None:
    """Поддерево глубже предела заменяется маркером, а не отдаётся как есть.

    Иначе секрет, до которого обход не дошёл, остался бы в логе открытым.
    """
    payload: dict[str, object] = {}
    current = payload
    for _ in range(MAX_DEPTH + 2):
        nested: dict[str, object] = {}
        current["nested"] = nested
        current = nested
    current["password"] = uuid4().hex

    probe: object = sanitize(payload, ["password"])
    while isinstance(probe, dict) and "nested" in probe:
        probe = probe["nested"]

    assert_that(probe).is_equal_to(DEPTH_EXCEEDED)


def test_masks_abbreviation_style_name() -> None:
    """Имя с аббревиатурой маскируется наравне со snake_case."""
    result = sanitize({"APIKey": "секрет"}, ["api_key"])

    assert_that(result["APIKey"]).is_equal_to(MASK)


def test_masks_name_with_digits() -> None:
    """Имя с цифрами маскируется независимо от стиля записи."""
    result = sanitize({"token2FA": "секрет"}, ["token_2_fa"])

    assert_that(result["token2FA"]).is_equal_to(MASK)


def test_masks_name_with_leading_underscore() -> None:
    """Ведущее подчёркивание не мешает распознать имя поля."""
    result = sanitize({"_accessToken": "секрет"}, ["access_token"])

    assert_that(result["_accessToken"]).is_equal_to(MASK)


def test_masks_non_latin_name() -> None:
    """Имя не на латинице тоже приводится к общему виду."""
    result = sanitize({"парольПользователя": "секрет"}, ["пароль_пользователя"])

    assert_that(result["парольПользователя"]).is_equal_to(MASK)


def test_masks_compound_secret_name() -> None:
    """Составное имя с типовым секретом в конце тоже маскируется."""
    result = sanitize({"userPassword": "секрет"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["userPassword"]).is_equal_to(MASK)


def test_masks_client_secret_field() -> None:
    """Типовое поле OpenID маскируется без дополнительной настройки."""
    result = sanitize({"clientSecret": "секрет"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["clientSecret"]).is_equal_to(MASK)


def test_keeps_field_that_merely_starts_with_secret_name() -> None:
    """Поле, лишь начинающееся с имени секрета, остаётся видимым."""
    result = sanitize({"tokenizer": "bpe"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["tokenizer"]).is_equal_to("bpe")


def test_masks_name_written_in_other_script() -> None:
    """Имя на другой письменности приводится к общему виду по свойствам Unicode."""
    result = sanitize({"κωδικόςΠρόσβασης": "секрет"}, ["κωδικός_πρόσβασης"])

    assert_that(result["κωδικόςΠρόσβασης"]).is_equal_to(MASK)
