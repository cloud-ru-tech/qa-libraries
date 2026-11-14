import pytest
from assertpy import assert_that
from logging_context.naming import (
    MAX_FILENAME_BYTES,
    build_test_id,
    build_test_name,
    hash_params,
    slugify,
)

PATH_SEPARATORS = ("/", "\\", "\0")


class FakeCallspec:
    def __init__(self, id_: str, params: dict[str, object]) -> None:
        """Initialize the object.

        :param id_: ``id_`` setting value.
        :param params: ``params`` setting value.
        """
        self.id = id_
        self.params = params


class FakeItem:
    def __init__(
        self,
        name: str,
        nodeid: str,
        original_name: str | None = None,
        callspec: FakeCallspec | None = None,
    ) -> None:
        """Initialize the object.

        :param name: ``name`` setting value.
        :param nodeid: ``nodeid`` setting value.
        :param original_name: ``original_name`` setting value.
        :param callspec: ``callspec`` setting value.
        """
        self.name = name
        self.nodeid = nodeid
        if original_name is not None:
            self.originalname = original_name
        if callspec is not None:
            self.callspec = callspec


def parametrized(name: str, nodeid: str, params_id: str, params: dict[str, object]) -> pytest.Item:
    original_name = name.split("[", maxsplit=1)[0]
    return FakeItem(name, nodeid, original_name, FakeCallspec(params_id, params))  # type: ignore[return-value]


def plain(name: str, nodeid: str) -> pytest.Item:
    return FakeItem(name, nodeid)  # type: ignore[return-value]


def test_keeps_readable_name_unchanged() -> None:
    assert_that(slugify("test_creates_invoice")).is_equal_to("test_creates_invoice")


def test_keeps_hashed_parameters_in_brackets() -> None:
    assert_that(slugify("test_par[abc123]")).is_equal_to("test_par[abc123]")


def test_replaces_forward_slash_in_name() -> None:
    assert_that(slugify("test_reads_a/b")).is_equal_to("test_reads_a_b")


def test_replaces_backslash_in_name() -> None:
    assert_that(slugify("test_reads_c\\d")).is_equal_to("test_reads_c_d")


def test_strips_parent_directory_reference() -> None:
    assert_that(slugify("../../secrets")).is_equal_to("secrets")


def test_neutralizes_parameter_escaping_the_brackets() -> None:
    assert_that(slugify("test_x[a[b]/../../outside]")).is_equal_to("test_x[a[b]_.._.._outside]")


def test_falls_back_for_name_without_allowed_characters() -> None:
    assert_that(slugify("проверка")).is_equal_to("unnamed")


def test_falls_back_for_empty_name() -> None:
    assert_that(slugify("")).is_equal_to("unnamed")


@pytest.mark.parametrize("dangerous", ["a/b", "e\\f", "../..", "g\0h", "/etc/passwd", "test[x]/../../out]"])
def test_never_yields_path_separators(dangerous: str) -> None:
    assert_that(slugify(dangerous)).does_not_contain(*PATH_SEPARATORS)


def test_limits_name_length_in_bytes() -> None:
    long_cyrillic_name = "проверка" * 200

    assert_that(len(slugify(long_cyrillic_name).encode())).described_as(
        "имя файла не должно превышать лимит файловой системы в байтах",
    ).is_less_than_or_equal_to(MAX_FILENAME_BYTES)


def test_keeps_truncated_names_distinguishable() -> None:
    prefix = "s" * 500

    assert_that(slugify(f"{prefix}_alpha")).is_not_equal_to(slugify(f"{prefix}_beta"))


def test_hashes_same_parameters_to_same_value() -> None:
    params_id = "currency-USD"

    assert_that(hash_params(params_id)).is_equal_to(hash_params(params_id))


def test_hashes_different_parameters_to_different_values() -> None:
    assert_that(hash_params("currency-USD")).is_not_equal_to(hash_params("currency-EUR"))


def test_names_unparametrized_test_by_its_own_name() -> None:
    item = plain("test_sends_receipt", "tests/test_billing.py::test_sends_receipt")

    assert_that(build_test_name(item)).is_equal_to("test_sends_receipt")


def test_replaces_parameters_in_name_with_their_hash() -> None:
    params_id = "3-EUR"
    item = parametrized("test_charges[3-EUR]", "tests/test_billing.py::test_charges[3-EUR]", params_id, {"amount": 3})

    assert_that(build_test_name(item)).is_equal_to(f"test_charges[{hash_params(params_id)}]")


def test_names_test_safely_when_parameter_escapes_the_brackets() -> None:
    item = parametrized(
        "test_uploads[a[b]/../../outside]",
        "tests/test_files.py::test_uploads[a[b]/../../outside]",
        "a[b]/../../outside",
        {"path": "a[b]/../../outside"},
    )

    assert_that(build_test_name(item)).does_not_contain(*PATH_SEPARATORS)


def test_identifies_unparametrized_test_by_its_nodeid() -> None:
    nodeid = "tests/test_search.py::test_finds_nothing"

    assert_that(build_test_id(plain("test_finds_nothing", nodeid))).is_equal_to(nodeid)


def test_identifies_parametrized_test_without_raw_parameters() -> None:
    params_id = "guest"
    item = parametrized("test_role[guest]", "tests/test_acl.py::test_role[guest]", params_id, {"role": "guest"})

    assert_that(build_test_id(item)).is_equal_to(f"tests/test_acl.py::test_role[{hash_params(params_id)}]")


def test_keeps_brackets_of_the_directory_path_intact() -> None:
    item = parametrized("test_ping[1]", "cases/[prod]/test_api.py::test_ping[1]", "1", {"attempt": 1})

    assert_that(build_test_id(item)).starts_with("cases/[prod]/")


def test_identifies_tests_from_bracketed_directories_differently() -> None:
    prod = parametrized("test_ping[1]", "cases/[prod]/test_api.py::test_ping[1]", "1", {"attempt": 1})
    stage = parametrized("test_ping[1]", "cases/[stage]/test_api.py::test_ping[1]", "1", {"attempt": 1})

    assert_that(build_test_id(prod)).is_not_equal_to(build_test_id(stage))


def test_identifies_different_parameter_sets_differently() -> None:
    first = parametrized("test_retries[1]", "tests/test_http.py::test_retries[1]", "1", {"times": 1})
    second = parametrized("test_retries[9]", "tests/test_http.py::test_retries[9]", "9", {"times": 9})

    assert_that(build_test_id(first)).is_not_equal_to(build_test_id(second))
