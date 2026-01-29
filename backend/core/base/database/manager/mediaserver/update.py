from sqlmodel import Session

from . import base
from core.base.database.models.mediaserver import (
    MediaServerRead,
    MediaServerUpdate,
)
from core.base.database.utils.engine import manage_session


@manage_session
def update(
    mediaserver_id: int,
    mediaserver_update: MediaServerUpdate,
    *,
    _session: Session = None,  # type: ignore
) -> MediaServerRead:
    """Update an existing media server in the database. \n
    Args:
        mediaserver_id (int): The id of the media server to update.
        mediaserver_update (MediaServerUpdate): The update data.
        _session (optional): Database session (auto-injected). \n
    Returns:
        MediaServerRead: The updated read-only media server object. \n
    Raises:
        ItemNotFoundError: If a media server with provided id does not exist.
    """
    db_mediaserver = base._get_db_item(mediaserver_id, _session=_session)
    mediaserver_update_data = mediaserver_update.model_dump(exclude_unset=True)
    db_mediaserver.sqlmodel_update(mediaserver_update_data)
    _session.add(db_mediaserver)
    _session.commit()
    _session.refresh(db_mediaserver)
    return MediaServerRead.model_validate(db_mediaserver)
