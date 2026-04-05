from fastapi import Request


def get_logged_user(request: Request):
    user_id = request.session.get("user_id")
    username = request.session.get("username")
    is_admin = request.session.get("is_admin", False)

    if not user_id or not username:
        return None

    return {
        "user_id": user_id,
        "username": username,
        "is_admin": bool(is_admin),
    }


def require_login(request: Request):
    return get_logged_user(request)


def is_admin(request: Request) -> bool:
    user = get_logged_user(request)
    return bool(user and user["is_admin"])