from humps import camelize, pascalize
from pydantic import BaseModel, ConfigDict


class CamelCaseBaseModel(BaseModel):
    """Модель, использующая camelCase при сериализации полей."""

    model_config = ConfigDict(
        alias_generator=camelize,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PascalCaseBaseModel(BaseModel):
    """Модель, использующая PascalCase при сериализации полей."""

    model_config = ConfigDict(
        alias_generator=pascalize,
        populate_by_name=True,
        serialize_by_alias=True,
    )
