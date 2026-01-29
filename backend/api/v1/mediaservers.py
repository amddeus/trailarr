from fastapi import APIRouter, HTTPException, status

from api.v1.models import ErrorResponse
from api.v1 import websockets
from app_logger import ModuleLogger
import core.base.database.manager.mediaserver as mediaserver_manager
from core.base.database.models.mediaserver import (
    MediaServerCreate,
    MediaServerRead,
    MediaServerUpdate,
)
from core.mediaserver.client import MediaServerClient

logger = ModuleLogger("MediaServersAPI")

mediaservers_router = APIRouter(prefix="/mediaservers", tags=["Media Servers"])


@mediaservers_router.get("/")
async def get_media_servers() -> list[MediaServerRead]:
    """Get all media servers. \n
    Returns:
        list[MediaServerRead]: List of all media servers.
    """
    return mediaserver_manager.read_all()


@mediaservers_router.post(
    "/test",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Media Server Connection Successful",
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Connection Failed",
        },
    },
)
async def test_media_server(mediaserver: MediaServerCreate) -> str:
    """Test a media server connection. \n
    Args:
        mediaserver (MediaServerCreate): The media server configuration to test. \n
    Returns:
        str: Success message with server info. \n
    Raises:
        HTTPException: If the connection fails.
    """
    try:
        temp_server = MediaServerRead(
            id=0,
            name=mediaserver.name,
            server_type=mediaserver.server_type,
            url=mediaserver.url,
            api_key=mediaserver.api_key,
            enabled=mediaserver.enabled,
            added_at=None,  # type: ignore
        )
        result = await MediaServerClient.test_connection(temp_server)
        return f"Connection Successful! {result}"
    except Exception as e:
        logger.error(f"Media server connection test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@mediaservers_router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {
            "description": "Media Server Created Successfully",
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Failed to Create Media Server",
        },
    },
)
async def create_media_server(mediaserver: MediaServerCreate) -> MediaServerRead:
    """Create a new media server. \n
    Args:
        mediaserver (MediaServerCreate): The media server configuration. \n
    Returns:
        MediaServerRead: The created media server. \n
    Raises:
        HTTPException: If creation fails.
    """
    try:
        result = mediaserver_manager.create(mediaserver)
        await websockets.ws_manager.broadcast(
            "Media Server Created Successfully!", "Success", reload="mediaservers"
        )
        return result
    except Exception as e:
        logger.error(f"Failed to create media server: {e}")
        await websockets.ws_manager.broadcast(
            "Failed to create Media Server!", "Error"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@mediaservers_router.get(
    "/{mediaserver_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Media Server Not Found",
        }
    },
)
async def get_media_server(mediaserver_id: int) -> MediaServerRead:
    """Get a media server by ID. \n
    Args:
        mediaserver_id (int): The ID of the media server. \n
    Returns:
        MediaServerRead: The media server. \n
    Raises:
        HTTPException: If the media server is not found.
    """
    try:
        return mediaserver_manager.read(mediaserver_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@mediaservers_router.put(
    "/{mediaserver_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Media Server Updated Successfully",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Media Server Not Found",
        },
    },
)
async def update_media_server(
    mediaserver_id: int, mediaserver: MediaServerUpdate
) -> MediaServerRead:
    """Update a media server. \n
    Args:
        mediaserver_id (int): The ID of the media server.
        mediaserver (MediaServerUpdate): The update data. \n
    Returns:
        MediaServerRead: The updated media server. \n
    Raises:
        HTTPException: If update fails.
    """
    try:
        result = mediaserver_manager.update(mediaserver_id, mediaserver)
        await websockets.ws_manager.broadcast(
            "Media Server Updated Successfully!", "Success", reload="mediaservers"
        )
        return result
    except Exception as e:
        logger.error(f"Failed to update media server: {e}")
        await websockets.ws_manager.broadcast(
            "Failed to update Media Server!", "Error"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@mediaservers_router.delete(
    "/{mediaserver_id}",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Media Server Deleted Successfully",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Media Server Not Found",
        },
    },
)
async def delete_media_server(mediaserver_id: int) -> str:
    """Delete a media server. \n
    Args:
        mediaserver_id (int): The ID of the media server. \n
    Returns:
        str: Success message. \n
    Raises:
        HTTPException: If deletion fails.
    """
    try:
        mediaserver_manager.delete(mediaserver_id)
        await websockets.ws_manager.broadcast(
            "Media Server Deleted Successfully!", "Success", reload="mediaservers"
        )
        return "Media Server Deleted Successfully!"
    except Exception as e:
        logger.error(f"Failed to delete media server: {e}")
        await websockets.ws_manager.broadcast(
            "Failed to delete Media Server!", "Error"
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@mediaservers_router.post(
    "/{mediaserver_id}/refresh",
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {
            "description": "Library Refresh Triggered Successfully",
        },
        status.HTTP_400_BAD_REQUEST: {
            "model": ErrorResponse,
            "description": "Failed to Trigger Refresh",
        },
        status.HTTP_404_NOT_FOUND: {
            "model": ErrorResponse,
            "description": "Media Server Not Found",
        },
    },
)
async def refresh_media_server_library(
    mediaserver_id: int, folder_path: str = ""
) -> str:
    """Trigger a library refresh on a media server. \n
    Args:
        mediaserver_id (int): The ID of the media server.
        folder_path (str): Optional folder path to refresh. \n
    Returns:
        str: Success message. \n
    Raises:
        HTTPException: If refresh fails.
    """
    try:
        server = mediaserver_manager.read(mediaserver_id)
        success = await MediaServerClient.refresh_library(server, folder_path)
        if success:
            return f"Library refresh triggered on '{server.name}'"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to trigger library refresh",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh media server library: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
