import os
import time
from functools import wraps

from authlib.integrations.flask_client import OAuth
from flask import Response, current_app, redirect, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

oauth = OAuth()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc

    if parsed < 0:
        raise RuntimeError(f"{name} must be greater than or equal to 0")

    return parsed


def csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)

    return [item.strip() for item in raw.split(",") if item.strip()]


def require_env(names: list[str]) -> None:
    missing = [name for name in names if not os.getenv(name)]

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required environment variable(s): {joined}")


def normalise_groups(value) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]

    if isinstance(value, list | tuple | set):
        return [str(item).strip() for item in value if str(item).strip()]

    return [str(value).strip()]


def configure_auth(app) -> None:
    auth_mode = os.getenv("AUTH_MODE", "none").strip().lower()

    if auth_mode not in {"none", "proxy", "oidc"}:
        raise RuntimeError("AUTH_MODE must be one of: none, proxy, oidc")

    app.config["AUTH_MODE"] = auth_mode

    secret_key = os.getenv("SECRET_KEY")
    if auth_mode == "oidc" and not secret_key:
        raise RuntimeError("SECRET_KEY is required when AUTH_MODE=oidc")

    if secret_key:
        app.config["SECRET_KEY"] = secret_key

    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    app.config["SESSION_COOKIE_SECURE"] = env_bool("SESSION_COOKIE_SECURE", False)
    app.config["OIDC_SESSION_MAX_AGE_SECONDS"] = env_int(
        "OIDC_SESSION_MAX_AGE_SECONDS",
        28_800,
    )
    app.config["PREFERRED_URL_SCHEME"] = (
        "https" if app.config["SESSION_COOKIE_SECURE"] else "http"
    )

    if env_bool("TRUST_PROXY_HEADERS", True):
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
            x_prefix=1,
        )

    if auth_mode != "oidc":
        return

    require_env(
        [
            "OIDC_CLIENT_ID",
            "OIDC_CLIENT_SECRET",
            "OIDC_DISCOVERY_URL",
        ]
    )

    oauth.init_app(app)
    oauth.register(
        name="authentik",
        client_id=os.getenv("OIDC_CLIENT_ID"),
        client_secret=os.getenv("OIDC_CLIENT_SECRET"),
        server_metadata_url=os.getenv("OIDC_DISCOVERY_URL"),
        client_kwargs={
            "scope": os.getenv("OIDC_SCOPES", "openid profile email"),
        },
    )


def public_url_for(endpoint: str, **values) -> str:
    public_base_url = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    path = url_for(endpoint, _external=False, **values)

    if public_base_url:
        return f"{public_base_url}{path}"

    return url_for(endpoint, _external=True, **values)


def current_path() -> str:
    if request.query_string:
        return request.full_path

    return request.path


def safe_next_url() -> str:
    next_url = request.args.get("next") or "/"

    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"

    return next_url


def oidc_session_is_expired() -> bool:
    max_age = current_app.config.get("OIDC_SESSION_MAX_AGE_SECONDS", 28_800)

    if max_age == 0:
        return False

    authenticated_at = session.get("authenticated_at")

    if authenticated_at is None:
        return True

    try:
        authenticated_at = float(authenticated_at)
    except (TypeError, ValueError):
        return True

    return time.time() - authenticated_at > max_age


def current_user() -> dict | None:
    auth_mode = current_app.config.get("AUTH_MODE", "none")
    oidc_user = session.get("user")

    if oidc_user:
        if auth_mode == "oidc" and oidc_session_is_expired():
            session.clear()
            return None

        return oidc_user

    if auth_mode != "proxy":
        return None

    proxy_user = (
        request.headers.get("X-Forwarded-User")
        or request.headers.get("Remote-User")
    )

    if proxy_user:
        return {
            "username": proxy_user,
            "email": request.headers.get("X-Forwarded-Email"),
            "groups": normalise_groups(request.headers.get("X-Forwarded-Groups")),
            "source": "proxy",
        }

    return None


def current_username() -> str:
    user = current_user()

    if not user:
        return "unknown"

    return (
        user.get("username")
        or user.get("preferred_username")
        or user.get("email")
        or user.get("sub")
        or "unknown"
    )


def user_is_allowed(user: dict) -> bool:
    allowed_groups = set(csv_env("OIDC_ALLOWED_GROUPS"))

    if not allowed_groups:
        return True

    user_groups = set(normalise_groups(user.get("groups")))

    return bool(user_groups.intersection(allowed_groups))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth_mode = current_app.config.get("AUTH_MODE", "none")

        if auth_mode == "none":
            return view(*args, **kwargs)

        user = current_user()

        if auth_mode == "proxy":
            if user:
                return view(*args, **kwargs)

            return Response("Authentication required", status=401)

        if auth_mode == "oidc":
            if not user:
                return redirect(url_for("login", next=current_path()))

            if not user_is_allowed(user):
                return Response("Forbidden", status=403)

            return view(*args, **kwargs)

        return Response("Invalid auth configuration", status=500)

    return wrapped


def register_auth_routes(app) -> None:
    @app.get("/login")
    def login():
        if current_app.config.get("AUTH_MODE") != "oidc":
            return redirect(url_for("index"))

        session["next_url"] = safe_next_url()
        redirect_uri = public_url_for("auth_callback")

        return oauth.authentik.authorize_redirect(redirect_uri)

    @app.get("/auth/callback")
    def auth_callback():
        if current_app.config.get("AUTH_MODE") != "oidc":
            return Response("OIDC authentication is not enabled", status=404)

        token = oauth.authentik.authorize_access_token()

        try:
            userinfo = dict(oauth.authentik.userinfo(token=token))
        except Exception:
            userinfo = dict(token.get("userinfo") or {})

        username_claim = os.getenv("OIDC_USERNAME_CLAIM", "preferred_username")
        groups_claim = os.getenv("OIDC_GROUPS_CLAIM", "groups")

        groups = normalise_groups(userinfo.get(groups_claim))

        user = {
            "sub": userinfo.get("sub"),
            "username": userinfo.get(username_claim)
            or userinfo.get("preferred_username")
            or userinfo.get("name")
            or userinfo.get("email"),
            "email": userinfo.get("email"),
            "groups": groups,
            "source": "oidc",
        }

        if not user_is_allowed(user):
            session.clear()
            return Response("Forbidden", status=403)

        session["user"] = user
        session["authenticated_at"] = time.time()

        return redirect(session.pop("next_url", "/"))

    @app.get("/logout")
    def logout():
        auth_mode = current_app.config.get("AUTH_MODE")
        session.clear()

        if auth_mode == "oidc":
            end_session_url = os.getenv("OIDC_END_SESSION_URL", "").strip()

            if end_session_url:
                return redirect(end_session_url)

        return redirect(url_for("index"))
