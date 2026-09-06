import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def gen_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """created_at/updated_at with Python-side (not server-side) defaults.

    Deliberate choice: a server_default=func.now() value isn't known to
    the ORM object until it's refreshed from the DB, which forces a lazy
    load the moment something (e.g. Pydantic serialization) touches the
    attribute — and outside an awaited context that raises MissingGreenlet
    under the async driver. Setting timestamps in Python keeps the object
    fully populated immediately after construction, no refresh needed.
    """

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
