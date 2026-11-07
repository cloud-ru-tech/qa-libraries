from collections.abc import Sequence
from typing import Protocol, cast

from assertpy import assert_that
from http_client.utils.sanitizer import sanitize
from pytest_cases import parametrize_with_cases

type SanitizeCase = tuple[object, list[str], object]


class _TypedDecorator(Protocol):
    def __call__[T](self, function: T) -> T: ...


def case_dict_property() -> SanitizeCase:
    return (
        {"password": "123123", "v": 123123},
        ["password"],
        {"password": "****", "v": 123123},
    )


def case_dict_inner_property() -> SanitizeCase:
    return (
        {"user": {"token": "abcd1234"}, "data": "test"},
        ["user.token"],
        {"user": {"token": "****"}, "data": "test"},
    )


def case_bare_name_inside_nested_object() -> SanitizeCase:
    return (
        {"profile": {"password": "nested-password", "name": "Ada"}},
        ["password"],
        {"profile": {"password": "****", "name": "Ada"}},
    )


def case_bare_name_inside_json_array() -> SanitizeCase:
    return (
        [{"credentials": {"token": "token-913"}}, {"token": "token-521", "enabled": True}],
        ["token"],
        [{"credentials": {"token": "****"}}, {"token": "****", "enabled": True}],
    )


def case_explicit_path_does_not_mask_other_branches() -> SanitizeCase:
    return (
        {"primary": {"token": "private-token"}, "secondary": {"token": "public-reference"}},
        ["primary.token"],
        {"primary": {"token": "****"}, "secondary": {"token": "public-reference"}},
    )


def case_two_dict_properties() -> SanitizeCase:
    return (
        {"account": {"number": "987654321"}, "info": {"email": "test@example.com"}},
        ["account.number", "info.email"],
        {"account": {"number": "****"}, "info": {"email": "****"}},
    )


def case_dict_properties_in_list() -> SanitizeCase:
    return (
        [{"id": 1, "name": "John Doe"}, {"id": 2, "name": "Jane Doe"}],
        ["*.name"],
        [{"id": 1, "name": "****"}, {"id": 2, "name": "****"}],
    )


def case_dict_properties_in_inner_list() -> SanitizeCase:
    return (
        {"credentials": [{"api_key": "key123"}, {"api_key": "key321"}]},
        ["credentials.*.api_key"],
        {"credentials": [{"api_key": "****"}, {"api_key": "****"}]},
    )


def case_only_second_dict_property_in_list() -> SanitizeCase:
    return (
        {"credentials": [{"api_key": "key123"}, {"api_key": "key321"}]},
        ["credentials.1.api_key", "details.address"],
        {"credentials": [{"api_key": "key123"}, {"api_key": "****"}]},
    )


def case_whole_branch_instead_of_leaf() -> SanitizeCase:
    return (
        {"card": {"number": "4111111111111111", "holder": "IVAN"}},
        ["card"],
        {"card": "****"},
    )


def case_no_sensitive_keys() -> SanitizeCase:
    return (
        {"login": "root", "shell": "/bin/zsh"},
        [],
        {"login": "root", "shell": "/bin/zsh"},
    )


def case_missing_key() -> SanitizeCase:
    return (
        {"login": "root"},
        ["profile.avatar"],
        {"login": "root"},
    )


def case_empty_dict() -> SanitizeCase:
    return ({}, ["password"], {})


def case_scalar_value() -> SanitizeCase:
    return ("just a string", ["password"], "just a string")


def case_none() -> SanitizeCase:
    return (None, ["key1.Key2"], None)


@cast("_TypedDecorator", parametrize_with_cases("value,sensitive_keys,expected", cases="."))
def test_sanitize(value: object, expected: object, sensitive_keys: Sequence[str]) -> None:
    sanitized_value = sanitize(value, sensitive_keys)

    assert_that(sanitized_value).is_equal_to(expected)


def test_keeps_original_nested_values_unchanged() -> None:
    original = {"credentials": [{"password": "original-secret"}]}

    sanitize(original, ["password"])

    assert_that(original).is_equal_to({"credentials": [{"password": "original-secret"}]})


def test_preserves_cyclic_object_references() -> None:
    original: dict[str, object] = {}
    original["next"] = original

    sanitized = sanitize(original, ["token"])

    assert_that(sanitized["next"]).is_same_as(sanitized)
