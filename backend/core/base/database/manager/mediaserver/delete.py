from sqlmodel import Session

from . import base
from core.base.database.utils.engine import manage_session


@manage_session
def delete(
    mediaserver_id: int,
    *,
    _session: Session = None,  # type: ignore
) -> bool:
    """Delete a media server from the database. \n
    Args:
        mediaserver_id (int): The id of the media server to delete.
        _session (optional): Database session (auto-injected). \n
    Returns:
        bool: True if the media server was deleted successfully. \n
    Raises:
        ItemNotFoundError: If a media server with provided id does not exist.
    """
    mediaserver = base._get_db_item(mediaserver_id, _session=_session)
    _session.delete(mediaserver)
    _session.commit()
    return True
