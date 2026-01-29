"""Notification service for media servers after trailer downloads."""

from app_logger import ModuleLogger
import core.base.database.manager.mediaserver as mediaserver_manager
from core.mediaserver.client import MediaServerClient

logger = ModuleLogger("MediaServerNotification")


async def notify_media_servers(folder_path: str) -> None:
    """Notify all enabled media servers to refresh their libraries. \n
    Args:
        folder_path (str): The folder path that was updated with a new trailer.
    """
    try:
        enabled_servers = mediaserver_manager.read_all_enabled()
        if not enabled_servers:
            logger.debug("No enabled media servers configured for notification")
            return

        for server in enabled_servers:
            try:
                logger.info(
                    f"Notifying media server '{server.name}' to refresh: {folder_path}"
                )
                success = await MediaServerClient.refresh_library(server, folder_path)
                if success:
                    logger.info(
                        f"Media server '{server.name}' notified successfully"
                    )
                else:
                    logger.warning(
                        f"Media server '{server.name}' notification may have failed"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to notify media server '{server.name}': {e}"
                )
    except Exception as e:
        logger.error(f"Failed to get enabled media servers: {e}")
