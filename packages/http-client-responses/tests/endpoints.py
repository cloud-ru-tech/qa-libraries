BASE_API_URL = "http://test.com"


def users_url(limit: int = 100, offset: int = 0) -> str:
    return f"{BASE_API_URL}/users?limit={limit}&offset={offset}"


def details_url(user_id: int) -> str:
    return f"{BASE_API_URL}/user/{user_id}/details"
