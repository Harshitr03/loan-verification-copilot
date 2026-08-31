from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from backend.app.config import get_settings
from backend.app.models import User

oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, h: str) -> bool:
    return bcrypt.checkpw(pw.encode(), h.encode())


def make_token(username: str, role: str) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=s.jwt_ttl_min)
    return jwt.encode({"sub": username, "role": role, "exp": exp}, s.jwt_secret, algorithm="HS256")


def decode_token(tok: str) -> dict:
    return jwt.decode(tok, get_settings().jwt_secret, algorithms=["HS256"])


async def get_current_user(token: str = Depends(oauth2)) -> User:
    cred_exc = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not token:
        raise cred_exc
    try:
        payload = decode_token(token)
    except JWTError:
        raise cred_exc
    user = await User.find_one(User.username == payload.get("sub"))
    if user is None:
        raise cred_exc
    return user


def require_role(*roles):
    async def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient role")
        return user
    return dep
