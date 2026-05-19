"""Tests for handle validation rules and uniqueness."""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.services.auth_service import validate_handle


# ── Validation rules ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("handle,expect_error", [
    ("alice",      False),
    ("alice_123",  False),
    ("abc",        False),   # minimum length 3
    ("a" * 32,     False),   # maximum length 32
    ("ab",         True),    # too short
    ("a" * 33,     True),    # too long
    ("Alice",      True),    # uppercase not allowed
    ("alice-bob",  True),    # hyphens not allowed
    ("alice bob",  True),    # spaces not allowed
    ("admin",      True),    # reserved
    ("livermore",  True),    # reserved
    ("me",         True),    # too short AND reserved
    ("",           True),    # empty
])
def test_handle_validation_rules(handle: str, expect_error: bool) -> None:
    err = validate_handle(handle)
    if expect_error:
        assert err is not None, f"Expected error for handle={handle!r} but got None"
    else:
        assert err is None, f"Expected no error for handle={handle!r} but got: {err}"


# ── Uniqueness (case-insensitive) ─────────────────────────────────────────────

def test_handle_uniqueness_case_insensitive(make_user, db: Session) -> None:
    from app.api.routes.me import patch_me
    from app.schemas.identity import PatchMeRequest

    user1 = make_user(email="h1@test.com", password="pw")
    user2 = make_user(email="h2@test.com", password="pw")

    # Assign handle to user1
    patch_me(body=PatchMeRequest(handle="myhandle"), current_user=user1, db=db)
    db.refresh(user1)
    assert user1.handle == "myhandle"

    # user2 tries to claim the same handle with different case
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        patch_me(body=PatchMeRequest(handle="MYHANDLE"), current_user=user2, db=db)
    assert exc_info.value.status_code == 409


def test_handle_stored_lowercase(make_user, db: Session) -> None:
    from app.api.routes.me import patch_me
    from app.schemas.identity import PatchMeRequest

    user = make_user(email="lower@test.com", password="pw")
    patch_me(body=PatchMeRequest(handle="MyHandle123"), current_user=user, db=db)
    db.refresh(user)
    assert user.handle == "myhandle123"


def test_user_can_re_set_own_handle(make_user, db: Session) -> None:
    from app.api.routes.me import patch_me
    from app.schemas.identity import PatchMeRequest

    user = make_user(email="reown@test.com", password="pw")
    patch_me(body=PatchMeRequest(handle="myown"), current_user=user, db=db)
    # Setting to same handle again should not 409
    result = patch_me(body=PatchMeRequest(handle="myown"), current_user=user, db=db)
    assert result.handle == "myown"
