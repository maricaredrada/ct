from __future__ import annotations

import functools
from typing import Any, Callable

from flask import Response, current_app, redirect, request, session, url_for


class AuthError(RuntimeError):
    pass


def verify_admin_token(id_token: str) -> dict[str, Any]:
    firebase_verifier = current_app.config.get("FIREBASE_VERIFIER")
    if not firebase_verifier:
        raise AuthError("Firebase authentication is not configured.")
    return firebase_verifier(id_token)


def admin_required(view: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        if not session.get("admin_id"):
            if request.path.startswith("/api/"):
                return Response("Unauthorized", status=401)
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped
