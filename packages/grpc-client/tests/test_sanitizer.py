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
    """A top-level field is masked by name."""
    result = sanitize({"login": "kettle", "password": "hot-water"}, ["password"])

    assert_that(result["password"]).is_equal_to(MASK)


def test_keeps_other_fields_intact() -> None:
    """Fields not listed remain unchanged."""
    result = sanitize({"login": "kettle", "password": "hot-water"}, ["password"])

    assert_that(result["login"]).is_equal_to("kettle")


def test_masks_nested_field_by_path() -> None:
    """A nested field is masked by its glom path."""
    result = sanitize({"account": {"secret": "moonlight"}}, ["account.secret"])

    assert_that(result["account"]["secret"]).is_equal_to(MASK)


def test_masks_field_in_every_list_item() -> None:
    """A field is masked in every list item."""
    result = sanitize({"keys": [{"value": "one"}, {"value": "two"}]}, ["keys.*.value"])

    assert_that([item["value"] for item in result["keys"]]).contains_only(MASK)


def test_keeps_source_unchanged() -> None:
    """The original structure is unchanged."""
    source = {"token": "original-value"}

    sanitize(source, ["token"])

    assert_that(source["token"]).is_equal_to("original-value")


def test_returns_copy_when_no_keys_given() -> None:
    """Without masking keys, a copy is returned rather than the original structure."""
    source = {"any": "value"}

    assert_that(sanitize(source, [])).is_not_same_as(source)


def test_masks_metadata_value_by_key() -> None:
    """A metadata value is masked by its key name."""
    result = sanitize_metadata({"authorization": "Bearer abc"}, ["authorization"])

    assert_that(dict(result)["authorization"]).is_equal_to(MASK)


def test_masks_metadata_key_ignoring_case() -> None:
    """Metadata key names are matched case-insensitively."""
    result = sanitize_metadata({"Authorization": "Bearer abc"}, ["authorization"])

    assert_that(dict(result)["Authorization"]).is_equal_to(MASK)


def test_masks_metadata_key_containing_dot() -> None:
    """A metadata key containing a dot is masked as a whole rather than parsed as a path.

    The gRPC specification allows dots in key names, so names cannot be treated as glom paths.
    """
    result = sanitize_metadata({"x.secret-token": "value-to-hide"}, ["x.secret-token"])

    assert_that(dict(result)["x.secret-token"]).is_equal_to(MASK)


def test_keeps_metadata_without_sensitive_keys() -> None:
    """Metadata without sensitive keys remains unchanged."""
    result = sanitize_metadata({"x-request-id": "req-17"}, ["authorization"])

    assert_that(dict(result)["x-request-id"]).is_equal_to("req-17")


def test_keeps_repeated_metadata_keys_after_masking() -> None:
    """Masking preserves all repeated keys."""
    result = sanitize_metadata([("x-key", "first"), ("x-key", "second")], ["x-key"])

    assert_that(result).is_length(2)


def test_masks_every_value_of_repeated_metadata_key() -> None:
    """Every value of a repeated key is masked, not just the first."""
    result = sanitize_metadata([("x-key", "first"), ("x-key", "second")], ["x-key"])

    assert_that([value for _, value in result]).contains_only(MASK)


def test_keeps_field_with_shifted_word_boundary() -> None:
    """A field with a different word boundary is not treated as a secret.

    protobuf serializes `sec_ret` as `secRet`: ignoring boundaries would match `secret`.
    """
    result = sanitize({"secRet": "не секрет"}, ["secret"])

    assert_that(result["secRet"]).is_equal_to("не секрет")


def test_masks_deeply_nested_payload_without_error() -> None:
    """A deeply nested message does not break log preparation."""
    payload: dict[str, object] = {}
    current = payload
    for _ in range(2000):
        nested: dict[str, object] = {}
        current["nested"] = nested
        current = nested

    assert_that(sanitize(payload, list(DEFAULT_SANITIZE_KEYS))).is_not_none()


def test_masks_nested_field_by_plain_name() -> None:
    """A field name without separators masks values at any nesting level."""
    result = sanitize({"user": {"password": "kitchen-key"}}, ["password"])

    assert_that(result["user"]["password"]).is_equal_to(MASK)


def test_masks_typical_secret_inside_nested_payload() -> None:
    """Common keys in nested message bodies are masked without additional configuration."""
    result = sanitize({"credentials": {"token": "field-secret"}}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["credentials"]["token"]).is_equal_to(MASK)


def test_masks_field_by_name_inside_list() -> None:
    """A field name also masks values inside lists."""
    result = sanitize({"items": [{"secret": "one"}, {"secret": "two"}]}, ["secret"])

    assert_that([item["secret"] for item in result["items"]]).contains_only(MASK)


def test_keeps_non_secret_fields_of_nested_payload() -> None:
    """Sibling fields in a nested object remain unchanged."""
    result = sanitize({"user": {"password": "hidden", "login": "visible"}}, ["password"])

    assert_that(result["user"]["login"]).is_equal_to("visible")


def test_masks_protobuf_camel_case_field() -> None:
    """A snake_case name masks a field serialized by protobuf in camelCase."""
    result = sanitize({"accessToken": "camel-secret"}, ["access_token"])

    assert_that(result["accessToken"]).is_equal_to(MASK)


def test_masks_typical_camel_case_secret_by_default() -> None:
    """Common secrets are masked in the form produced by protobuf."""
    result = sanitize({"user": {"refreshToken": "renew-me"}}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["user"]["refreshToken"]).is_equal_to(MASK)


def test_keeps_field_with_similar_name() -> None:
    """A field with a similar but different name remains unchanged."""
    result = sanitize({"accessCount": 42}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["accessCount"]).is_equal_to(42)


def test_masks_subtree_beyond_depth_limit() -> None:
    """A subtree beyond the depth limit is replaced with a marker rather than returned unchanged.

    Otherwise a secret not reached by traversal would remain visible in the log.
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
    """A name containing an acronym is masked like snake_case."""
    result = sanitize({"APIKey": "секрет"}, ["api_key"])

    assert_that(result["APIKey"]).is_equal_to(MASK)


def test_masks_name_with_digits() -> None:
    """A name containing digits is masked regardless of naming style."""
    result = sanitize({"token2FA": "секрет"}, ["token_2_fa"])

    assert_that(result["token2FA"]).is_equal_to(MASK)


def test_masks_name_with_leading_underscore() -> None:
    """A leading underscore does not prevent field name recognition."""
    result = sanitize({"_accessToken": "секрет"}, ["access_token"])

    assert_that(result["_accessToken"]).is_equal_to(MASK)


def test_masks_non_latin_name() -> None:
    """Non-Latin names are also normalized."""
    result = sanitize({"парольПользователя": "секрет"}, ["пароль_пользователя"])

    assert_that(result["парольПользователя"]).is_equal_to(MASK)


def test_masks_compound_secret_name() -> None:
    """A compound name ending in a common secret is also masked."""
    result = sanitize({"userPassword": "секрет"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["userPassword"]).is_equal_to(MASK)


def test_masks_client_secret_field() -> None:
    """A common OpenID field is masked without additional configuration."""
    result = sanitize({"clientSecret": "секрет"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["clientSecret"]).is_equal_to(MASK)


def test_keeps_field_that_merely_starts_with_secret_name() -> None:
    """A field that merely starts with a secret name remains visible."""
    result = sanitize({"tokenizer": "bpe"}, list(DEFAULT_SANITIZE_KEYS))

    assert_that(result["tokenizer"]).is_equal_to("bpe")


def test_masks_name_written_in_other_script() -> None:
    """A name in another script is normalized using Unicode properties."""
    result = sanitize({"κωδικόςΠρόσβασης": "секрет"}, ["κωδικός_πρόσβασης"])

    assert_that(result["κωδικόςΠρόσβασης"]).is_equal_to(MASK)
