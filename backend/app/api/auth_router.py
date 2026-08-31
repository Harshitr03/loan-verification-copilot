from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from backend.app.models import User
from backend.app.auth import verify_password, make_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(form: OAuth2PasswordRequestForm = Depends()):
    user = await User.find_one(User.username == form.username)
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    return {"access_token": make_token(user.username, user.role),
            "token_type": "bearer", "role": user.role}
