from sqlmodel import Session

from core.base.database.models.mediaserver import (
    MediaServer,
    MediaServerCreate,
    MediaServerRead,
)
from core.base.database.utils.engine import manage_session


@manage_session
def create(
    mediaserver: MediaServerCreate,
    *,
    _session: Session = None,  # type: ignore
) -> MediaServerRead:
    """Create a new media server in the database. \n
    Args:
        mediaserver (MediaServerCreate): The media server to create.
        _session (optional): Database session (auto-injected). \n
    Returns:
        MediaServerRead: The created media server object.
    """
    db_mediaserver = MediaServer.model_validate(mediaserver)
    _session.add(db_mediaserver)
    _session.commit()
    _session.refresh(db_mediaserver)
    return MediaServerRead.model_validate(db_mediaserver)
