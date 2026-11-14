from humps import camelize, pascalize
from pydantic import BaseModel, ConfigDict


class CamelCaseBaseModel(BaseModel):
    """Model that serializes fields in camelCase."""

    model_config = ConfigDict(
        alias_generator=camelize,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class PascalCaseBaseModel(BaseModel):
    """Model that serializes fields in PascalCase."""

    model_config = ConfigDict(
        alias_generator=pascalize,
        populate_by_name=True,
        serialize_by_alias=True,
    )
