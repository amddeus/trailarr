from sqlmodel import Session, select

from core.base.database.models.mediaserver import MediaServer
from core.base.database.utils.engine import manage_session
from exceptions import ItemNotFoundError


@manage_session
def _get_db_item(
    mediaserver_id: int,
    *,
    _session: Session = None,  # type: ignore
) -> MediaServer:
    """Get a media server from the database. \n
    Args:
        mediaserver_id (int): The id of the media server to get.
        _session (optional): Database session (auto-injected). \n
    Returns:
        MediaServer: The database media server object. \n
    Raises:
        ItemNotFoundError: If a media server with provided id does not exist.
    """
    statement = select(MediaServer).where(MediaServer.id == mediaserver_id)
    mediaserver = _session.exec(statement).first()
    if not mediaserver:
        raise ItemNotFoundError("MediaServer", mediaserver_id)
    return mediaserver


@manage_session
def exists(
    mediaserver_id: int,
    *,
    _session: Session = None,  # type: ignore
) -> bool:
    """Check if a media server exists in the database. \n
    Args:
        mediaserver_id (int): The id of the media server to check.
        _session (optional): Database session (auto-injected). \n
    Returns:
        bool: True if the media server exists, False otherwise.
    """
    statement = select(MediaServer).where(MediaServer.id == mediaserver_id)
    mediaserver = _session.exec(statement).first()
    return mediaserver is not None
