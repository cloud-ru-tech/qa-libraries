from datetime import datetime

from pydantic import BaseModel


class ExampleRequest(BaseModel):
    limit: int = 100
    offset: int = 0
    search: str | None = None


class User(BaseModel):
    name: str
    age: int
    alive: bool
    skills: list[str]
    created_at: datetime


class ExampleResponse(BaseModel):
    users: list[User]
    total: int
