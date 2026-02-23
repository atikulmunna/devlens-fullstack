from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import User
from app.deps import get_current_user
from app.services.tokens import create_access_token


def test_get_current_user_requires_credentials(db_session: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=None, db=db_session)
    assert exc.value.status_code == 401


def test_get_current_user_resolves_user(db_session: Session) -> None:
    user = User(
        id=uuid4(),
        github_id=900000090,
        username="dep-user",
        email="dep@test.dev",
        avatar_url=None,
    )
    db_session.add(user)
    db_session.commit()

    class Creds:
        credentials = create_access_token(user.id)

    resolved = get_current_user(credentials=Creds(), db=db_session)
    assert resolved.id == user.id
