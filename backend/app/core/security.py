"""Lightweight JWT auth + RBAC for the take-home.

Production note (see architecture.md §8 and roadmap.md): this is a
self-contained JWT issuer with a hardcoded demo user store so the API is
independently runnable/testable without external IdP setup. The
dependency shape (`get_current_user`, `require_roles`) is what would stay
stable if this were swapped for real OIDC/SSO — only token *issuance*
would change.
"""
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import settings


class Role(StrEnum):
    ADMIN = "admin"
    APPROVER = "approver"
    OPERATOR = "operator"
    VIEWER = "viewer"


class DemoUser(BaseModel):
    username: str
    roles: list[Role]


_DEMO_USERS: dict[str, DemoUser] = {
    "admin": DemoUser(username="admin", roles=[Role.ADMIN]),
    "approver": DemoUser(username="approver", roles=[Role.APPROVER]),
    "operator": DemoUser(username="operator", roles=[Role.OPERATOR]),
    "viewer": DemoUser(username="viewer", roles=[Role.VIEWER]),
}

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def authenticate_demo_user(username: str) -> DemoUser | None:
    """Demo auth: username IS the password, and identifies the role.
    Never used in production — see roadmap.md for the real-SSO item."""
    return _DEMO_USERS.get(username)


def create_access_token(user: DemoUser) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": user.username,
        "roles": [r.value for r in user.roles],
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(token: str = Depends(oauth2_scheme)) -> DemoUser:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        username: str = payload["sub"]
        roles = [Role(r) for r in payload.get("roles", [])]
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc
    return DemoUser(username=username, roles=roles)


def require_roles(*allowed: Role):
    """Dependency factory: `Depends(require_roles(Role.APPROVER, Role.ADMIN))`."""

    def _dependency(user: DemoUser = Depends(get_current_user)) -> DemoUser:
        if not any(r in user.roles for r in allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {[r.value for r in allowed]}",
            )
        return user

    return _dependency
