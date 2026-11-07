from assertpy import assert_that
from pydantic_extensions.fields import CamelCaseBaseModel, PascalCaseBaseModel


class UserCamelCase(CamelCaseBaseModel):
    username: str
    last_name: str
    is_active: bool


class UserPascalCase(PascalCaseBaseModel):
    username: str
    last_name: str
    is_active: bool


def test_serialize_to_camel_case() -> None:
    """Проверка сериализации полей в camelCase при использовании CamelCaseBaseModel."""
    user = UserCamelCase(username="John", last_name="Doe", is_active=True)

    user_json = user.model_dump_json()

    assert_that(user_json).is_equal_to('{"username":"John","lastName":"Doe","isActive":true}')


def test_deserialize_from_camel_case() -> None:
    """Проверка десериализации полей из camelCase при использовании CamelCaseBaseModel."""
    user_json = '{"username":"John","lastName":"Doe","isActive":true}'

    user = UserCamelCase.model_validate_json(user_json)

    assert_that(user.username).is_equal_to("John")
    assert_that(user.last_name).is_equal_to("Doe")
    assert_that(user.is_active).is_true()


def test_serialize_to_pascal_case() -> None:
    """Проверка сериализации полей в PascalCase при использовании PascalCaseBaseModel."""
    user = UserPascalCase(username="John", last_name="Doe", is_active=True)

    user_json = user.model_dump_json()

    assert_that(user_json).is_equal_to('{"Username":"John","LastName":"Doe","IsActive":true}')


def test_deserialize_from_pascal_case() -> None:
    """Проверка десериализации полей из PascalCase при использовании PascalCaseBaseModel."""
    user_json = '{"Username":"John","LastName":"Doe","IsActive":true}'

    user = UserPascalCase.model_validate_json(user_json)

    assert_that(user.username).is_equal_to("John")
    assert_that(user.last_name).is_equal_to("Doe")
    assert_that(user.is_active).is_true()
