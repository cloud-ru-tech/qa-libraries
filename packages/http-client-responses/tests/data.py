def user(
    name: str,
    age: int = 30,
    skills: list[str] | None = None,
    created_at: str = "2024-01-01T00:00:00",
) -> dict[str, object]:
    return {
        "name": name,
        "age": age,
        "alive": True,
        "skills": ["Python"] if skills is None else skills,
        "created_at": created_at,
    }


def users_payload(*users: dict[str, object]) -> dict[str, object]:
    return {"users": list(users), "total": len(users)}


def details_body(**fields: str) -> bytes:
    return "\n".join(f"{key}: {value}" for key, value in fields.items()).encode()
