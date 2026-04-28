"""Login/logout endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.auth import make_session_cookie, verify_password

router = APIRouter()


class LoginIn(BaseModel):
    password: str


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response):
    settings = request.app.state.settings
    if not verify_password(settings.password, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad password")

    cookie_value = make_session_cookie(settings.secret, ttl_sec=settings.cookie_max_age_sec)
    response.set_cookie(
        key=settings.cookie_name,
        value=cookie_value,
        max_age=settings.cookie_max_age_sec,
        httponly=True,
        secure=not settings.dev_mode,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    settings = request.app.state.settings
    response.delete_cookie(
        key=settings.cookie_name,
        path="/",
        httponly=True,
        secure=not settings.dev_mode,
        samesite="lax",
    )
    return {"ok": True}
