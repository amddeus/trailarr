from sqlmodel import Session, select

from . import base
from core.base.database.models.mediaserver import (
    MediaServer,
    MediaServerRead,
)
from core.base.database.utils.engine import manage_session


@manage_session
def read(
    mediaserver_id: int,
    *,
    _session: Session = None,  # type: ignore
) -> MediaServerRead:
    """Read a media server from the database. \n
    Args:
        mediaserver_id (int): The id of the media server to read.
        _session (optional): Database session (auto-injected). \n
    Returns:
        MediaServerRead: The read-only media server object. \n
    Raises:
        ItemNotFoundError: If a media server with provided id does not exist.
    """
    mediaserver = base._get_db_item(mediaserver_id, _session=_session)
    return MediaServerRead.model_validate(mediaserver)


@manage_session
def read_all(
    *,
    _session: Session = None,  # type: ignore
) -> list[MediaServerRead]:
    """Read all media servers from the database. \n
    Args:
        _session (optional): Database session (auto-injected). \n
    Returns:
        list[MediaServerRead]: A list of read-only media server objects.
    """
    statement = select(MediaServer)
    mediaservers = _session.exec(statement).all()
    return [
        MediaServerRead.model_validate(mediaserver)
        for mediaserver in mediaservers
    ]


@manage_session
def read_all_enabled(
    *,
    _session: Session = None,  # type: ignore
) -> list[MediaServerRead]:
    """Read all enabled media servers from the database. \n
    Args:
        _session (optional): Database session (auto-injected). \n
    Returns:
        list[MediaServerRead]: A list of enabled read-only media server objects.
    """
    statement = select(MediaServer).where(MediaServer.enabled == True)  # noqa: E712
    mediaservers = _session.exec(statement).all()
    return [
        MediaServerRead.model_validate(mediaserver)
        for mediaserver in mediaservers
    ]
