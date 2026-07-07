"""Authentication helpers: password hashing and JWT tokens.

Kept deliberately small and readable:
  * passwords are hashed with PBKDF2 from the standard library (no bcrypt dep);
  * tokens are standard JWTs signed with a shared secret (PyJWT).

The OAuth2 "password" flow: POST username+password to /token, get back a JWT,
then send it as ``Authorization: Bearer <token>`` on every protected request.
"""

import hashlib
import hmac
import os
import time

import jwt
from fastapi import HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# Demo secret (>=32 bytes for HS256). In production this comes from a config /
# secret manager and is never committed to code.
SECRET_KEY = "dev-secret-change-me-in-production-0123456789"
ALGORITHM = "HS256"
TOKEN_TTL_SECONDS = 3600

# Tells FastAPI/Swagger where to obtain a token and how to read the header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


def hash_password(password: str, salt: str | None = None) -> str:
    """Return ``salt$digest``. A random salt is generated when hashing anew."""
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    salt, _ = stored.split("$", 1)
    # compare_digest avoids timing attacks.
    return hmac.compare_digest(hash_password(password, salt), stored)


def create_access_token(user_id: str, tenant_id: str) -> str:
    payload = {
        "sub": user_id,               # subject = the user id
        "tenant": tenant_id,          # tenant travels inside the token
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
