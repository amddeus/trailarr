"""Trailer download module using Apple TV as the source."""

from datetime import datetime, timezone
import os

import requests
from api.v1 import websockets
from app_logger import ModuleLogger
import core.base.database.manager.media as media_manager
from core.base.database.models.helpers import MediaUpdateDC
from core.base.database.models.media import MediaRead, MonitorStatus
from core.base.database.models.trailerprofile import TrailerProfileRead
from core.download.trailers.service import record_new_trailer_download
from core.download.apple.downloader import download_apple_trailer
from core.download.apple.api import TrailerInfo, AppleTVPlus
from core.download import trailer_file, trailer_search, video_analysis
from exceptions import DownloadFailedError

logger = ModuleLogger("TrailersDownloader")


def _get_trailer_from_manual_id(
    apple_id: str, media_title: str, is_movie: bool = True
) -> TrailerInfo | None:
    """Get trailer info directly from a manually provided Apple TV ID/URL.

    This function is used when the user explicitly provides an Apple TV
    content ID or URL, bypassing the unreliable auto-search.

    Args:
        apple_id: Apple TV content ID (umc.cmc.xxx) or full URL.
        media_title: The media title for logging purposes.
        is_movie: Whether this is a movie (True) or TV show (False).

    Returns:
        TrailerInfo if found, None otherwise.
    """
    if not apple_id:
        return None

    # Construct URL if only ID is provided
    if apple_id.startswith("umc."):
        media_type = "movie" if is_movie else "show"
        content_url = f"https://tv.apple.com/us/{media_type}/-/{apple_id}"
    elif apple_id.startswith("http"):
        content_url = apple_id
    else:
        logger.warning(f"Invalid Apple TV ID format: {apple_id}")
        return None

    logger.info(
        f"Using manually provided Apple TV URL for '{media_title}': {content_url}"
    )

    try:
        atvp = AppleTVPlus()
        trailers = atvp.get_trailers(content_url, default_only=True)
        if trailers:
            logger.info(f"Found trailer: {trailers[0].video_title}")
            return trailers[0]
        logger.warning(f"No trailer found at URL: {content_url}")
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.error(f"Failed to fetch trailer from {content_url}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching trailer from {content_url}: {e}")

    return None


def __update_media_status(
    media: MediaRead,
    status_type: MonitorStatus,
    profile: TrailerProfileRead,
    apple_id: str | None = None,
):
    """Update the media status in the database."""
    if status_type == MonitorStatus.DOWNLOADING:
        update = MediaUpdateDC(
            id=media.id,
            monitor=True,
            status=MonitorStatus.DOWNLOADING,
        )
        if profile.stop_monitoring and apple_id:
            update.yt_id = apple_id
    elif status_type == MonitorStatus.DOWNLOADED:
        _monitor = True
        if profile.stop_monitoring:
            _monitor = False
        update = MediaUpdateDC(
            id=media.id,
            monitor=_monitor,
            status=MonitorStatus.DOWNLOADED,
            trailer_exists=profile.stop_monitoring,
            downloaded_at=datetime.now(timezone.utc),
        )
        if profile.stop_monitoring and apple_id:
            update.yt_id = apple_id
    elif status_type == MonitorStatus.MISSING:
        update = MediaUpdateDC(
            id=media.id,
            monitor=True,
            status=MonitorStatus.MISSING,
        )
        if media.trailer_exists:
            update = MediaUpdateDC(
                id=media.id,
                monitor=False,
                status=MonitorStatus.DOWNLOADED,
            )
    else:
        return None
    media_manager.update_media_status(update)
    return None


async def __download_and_verify_trailer(
    media: MediaRead,
    trailer_info: TrailerInfo,
    profile: TrailerProfileRead,
) -> str:
    """Download the trailer from Apple TV and verify it."""
    logger.info(
        f"Downloading trailer for '{media.title}' [{media.id}] "
        f"from Apple TV: {trailer_info.video_title}"
    )
    tmp_dir = "/var/lib/trailarr/tmp"
    if not os.path.exists(tmp_dir):
        tmp_dir = "/app/tmp"
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)

    output_file = f"{tmp_dir}/{media.id}-trailer.{profile.file_format}"

    output_file = await download_apple_trailer(
        trailer_info, output_file, profile
    )

    if not trailer_file.verify_download(output_file, media.title, profile):
        raise DownloadFailedError("Trailer verification failed")

    if profile.remove_silence:
        output_file = video_analysis.remove_silence_at_end(output_file)

    return output_file


async def download_trailer(
    media: MediaRead,
    profile: TrailerProfileRead,
    retry_count: int = 2,
    exclude: list[str] | None = None,
) -> bool:
    """Download trailer for a media object with given profile from Apple TV.
    Args:
        media (MediaRead): The media object to download the trailer for.
        profile (TrailerProfileRead): The trailer profile to use.
        retry_count (int, optional): Number of retries if download fails.
        exclude (list[str], optional): List of Apple IDs to exclude.
    Returns:
        bool: True if trailer download was successful, False otherwise.
    Raises:
        DownloadFailedError: If trailer download fails.
    """
    logger.info(f"Downloading trailer for '{media.title}' [{media.id}]")
    if not exclude:
        exclude = []

    trailer_info = None
    manual_id_provided = False

    # Strategy 1: If a manual Apple TV ID/URL was provided, use it directly
    # This bypasses the unreliable search and uses the user's explicit choice
    # Note: youtube_trailer_id field is repurposed for Apple TV IDs
    if media.youtube_trailer_id:
        # Check if this is a manually provided ID (starts with umc. or http)
        # vs an existing stored ID from a previous download
        apple_id = media.youtube_trailer_id
        if apple_id.startswith("umc.") or apple_id.startswith("http"):
            manual_id_provided = True
            trailer_info = _get_trailer_from_manual_id(
                apple_id, media.title, media.is_movie
            )

    # Strategy 2: Search for trailer on Apple TV if no manual ID or it failed
    if not trailer_info:
        # Only exclude the current trailer ID for re-downloads (not for manual IDs)
        if media.trailer_exists and media.youtube_trailer_id and not manual_id_provided:
            exclude.append(media.youtube_trailer_id)

        trailer_info = trailer_search.get_trailer_info(media, profile, exclude)

    if not trailer_info:
        error_msg = (
            f"No trailer found for '{media.title}'. "
            "Try providing the Apple TV URL manually (e.g., "
            "https://tv.apple.com/us/movie/movie-name/umc.cmc.xxx)"
        )
        raise DownloadFailedError(error_msg)

    apple_id = trailer_info.apple_id or ""

    try:
        __update_media_status(
            media, MonitorStatus.DOWNLOADING, profile, apple_id
        )

        # Download the trailer and verify
        output_file = await __download_and_verify_trailer(
            media, trailer_info, profile
        )

        # Move the trailer to the media folder
        final_path = trailer_file.move_trailer_to_folder(
            output_file, media, profile
        )

        __update_media_status(
            media, MonitorStatus.DOWNLOADED, profile, apple_id
        )

        # Record the download in the database
        await record_new_trailer_download(
            media, profile.id, final_path, apple_id
        )

        msg = (
            f"Trailer downloaded successfully for '{media.title}' [{media.id}]"
            f" from Apple TV ({trailer_info.video_title})"
        )
        logger.info(msg)
        await websockets.ws_manager.broadcast(msg, "Success", reload="media")
        return True

    except Exception as e:
        logger.exception(f"Failed to download trailer: {e}")
        __update_media_status(media, MonitorStatus.MISSING, profile, apple_id)

        if retry_count > 0:
            logger.info(
                f"Retrying download for '{media.title}'... "
                f"({3 - retry_count}/3)"
            )
            if apple_id:
                exclude.append(apple_id)
            return await download_trailer(
                media, profile, retry_count - 1, exclude
            )

        raise DownloadFailedError(
            f"Failed to download trailer for '{media.title}'"
        )
