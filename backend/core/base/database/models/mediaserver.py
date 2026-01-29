from datetime import datetime, timezone
from enum import Enum

from pydantic import field_validator
from sqlmodel import Field

from core.base.database.models.base import AppSQLModel


def get_current_time():
    return datetime.now(timezone.utc)


class MediaServerType(str, Enum):
    """Enum for different media server types."""

    EMBY = "emby"
    JELLYFIN = "jellyfin"
    PLEX = "plex"


class MediaServerBase(AppSQLModel):
    """Base class for the MediaServer model. \n
    Note: \n
        🚨**DO NOT USE THIS CLASS DIRECTLY.**🚨 \n
    Use MediaServerCreate, MediaServerRead, or MediaServerUpdate instead.
    """

    name: str
    server_type: MediaServerType
    url: str
    api_key: str
    enabled: bool = True


class MediaServer(MediaServerBase, table=True):
    """MediaServer model for the database. \n
    Note: \n
        🚨**DO NOT USE THIS CLASS DIRECTLY.**🚨 \n
    Use MediaServerCreate, MediaServerRead, or MediaServerUpdate instead.
    """

    id: int | None = Field(default=None, primary_key=True)
    added_at: datetime = Field(default_factory=get_current_time)


class MediaServerCreate(MediaServerBase):
    """MediaServer model for creating a new media server."""

    pass


class MediaServerRead(MediaServerBase):
    """MediaServer model for reading a media server."""

    id: int
    added_at: datetime

    @field_validator("added_at", mode="after")
    @classmethod
    def correct_timezone(cls, value: datetime) -> datetime:
        return cls.set_timezone_to_utc(value)


class MediaServerUpdate(AppSQLModel):
    """MediaServer model for updating a media server."""

    name: str | None = None
    server_type: MediaServerType | None = None
    url: str | None = None
    api_key: str | None = None
    enabled: bool | None = None
