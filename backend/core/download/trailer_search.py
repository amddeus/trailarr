"""Trailer search module using Apple TV as the source."""

from app_logger import ModuleLogger
from core.base.database.models.media import MediaRead
from core.base.database.models.trailerprofile import TrailerProfileRead
from core.download.apple.api import TrailerInfo
from core.download.apple.search import search_for_trailer as apple_search

logger = ModuleLogger("TrailersDownloader")


def search_for_trailer(
    media: MediaRead,
    profile: TrailerProfileRead,
) -> str | None:
    """Search for trailer ID for the media object from Apple TV. \n
    Args:
        media (MediaRead): Media object.
        profile (TrailerProfileRead): The trailer profile to use.
    Returns:
        str | None: Apple TV trailer ID if found, else None.
    """
    trailer_info = apple_search(media, exclude=[])
    
    if not trailer_info:
        return None
    
    return trailer_info.apple_id


def get_trailer_info(
    media: MediaRead,
    profile: TrailerProfileRead,
    exclude: list[str] | None = None,
) -> TrailerInfo | None:
    """Get trailer information for the media object from Apple TV. \n
    Args:
        media (MediaRead): Media object.
        profile (TrailerProfileRead): The trailer profile to use.
        exclude (list[str], Optional=None): List of Apple IDs to exclude.
    Returns:
        TrailerInfo | None: Trailer info object / None if not found.
    """
    if not exclude:
        exclude = []

    # Search for trailer on Apple TV
    trailer_info = apple_search(media, exclude)

    if not trailer_info:
        filter_name = (
            profile.customfilter.filter_name
            if profile.customfilter
            else "unknown"
        )
        logger.warning(
            f"No trailer found for '{media.title}' [{media.id}] "
            f"with profile '{filter_name}'."
        )
        return None

    # Check if trailer is in exclude list
    if trailer_info.apple_id and trailer_info.apple_id in exclude:
        logger.debug(
            f"Trailer {trailer_info.apple_id} is in exclude list"
        )
        return None

    logger.info(
        f"Found trailer for '{media.title}': {trailer_info.video_title}"
    )
    return trailer_info
