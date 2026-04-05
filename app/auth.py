from fastapi import Request


def get_logged_user(request: Request):
    return request.session.get("username")


def require_login(request: Request):
    return get_logged_user(request)