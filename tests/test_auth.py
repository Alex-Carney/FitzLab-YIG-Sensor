import time

import pytest

from app.auth import (
    SessionInvalidError,
    make_session_cookie,
    verify_session_cookie,
    verify_password,
)


SECRET = "x" * 32


def test_make_and_verify_session():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    payload = verify_session_cookie(SECRET, cookie)
    assert "exp" in payload
    assert payload["exp"] > int(time.time())


def test_verify_session_rejects_tampered():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    head, sig = cookie.split(".")
    bad = head + "." + ("A" if sig[0] != "A" else "B") + sig[1:]
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, bad)


def test_verify_session_rejects_expired():
    cookie = make_session_cookie(SECRET, ttl_sec=-10)
    with pytest.raises(SessionInvalidError, match="expired"):
        verify_session_cookie(SECRET, cookie)


def test_verify_session_rejects_garbage():
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, "garbage")
    with pytest.raises(SessionInvalidError):
        verify_session_cookie(SECRET, "")


def test_verify_session_rejects_wrong_secret():
    cookie = make_session_cookie(SECRET, ttl_sec=3600)
    with pytest.raises(SessionInvalidError):
        verify_session_cookie("y" * 32, cookie)


def test_verify_password_constant_time():
    assert verify_password("hunter2", "hunter2") is True
    assert verify_password("hunter2", "wrong") is False
    assert verify_password("hunter2", "") is False
