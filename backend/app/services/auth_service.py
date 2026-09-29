"""
services/auth_service.py
------------------------
Business logic for user authentication.
Designed so that an SSO provider can be plugged in later without touching
the route layer — just swap out authenticate_user().
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import decode_token, hash_password, verify_password
from ..models.user import User
from ..schemas.auth import UserCreate

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def create_user(db: Session, payload: UserCreate) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, identifier: str, password: str) -> User | None:
    """
    Local password authentication.
    'identifier' can be either an email address or a username.
    Returns the User on success, None on failure.
    SSO: replace or extend this function — routes stay the same.
    """
    # Try email first (case-insensitive), then username
    user = (
        db.query(User).filter(User.email == identifier.lower()).first()
        or db.query(User).filter(User.username == identifier).first()
    )
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency — resolves the logged-in user from the JWT."""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
