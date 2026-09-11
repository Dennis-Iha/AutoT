"""Phase 19: password hashing + JWT issuance/verification.

Uses the ``bcrypt`` package directly rather than passlib's CryptContext:
passlib 1.7.4 (last released 2020, effectively unmaintained) probes
``bcrypt.__about__.__version__`` to detect the backend version, which
recent bcrypt releases (this environment installed 5.0.0) no longer
expose - a real, encountered failure, not hypothetical: it silently
mis-detects the backend and then raises "password cannot be longer than 72
bytes" even for short passwords. Calling bcrypt directly sidesteps
passlib's broken version-sniffing entirely.

The signing secret MUST come from the environment in any real deployment -
the default here is explicitly a dev-only placeholder that is at least
never silently written to disk or checked into the model registry (unlike
the checksums in Phase 10, which are meant to be public).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import User

SECRET_KEY = os.environ.get("AT_JWT_SECRET", "dev-only-insecure-secret-do-not-use-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": subject, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the subject (user id). Raises jwt exceptions on invalid/expired tokens."""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    return payload["sub"]


def get_current_user(
    token: str = Depends(_oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise credentials_error from exc

    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
    return user
