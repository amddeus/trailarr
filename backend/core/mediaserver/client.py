"""Media server client for communicating with Emby, Jellyfin, and Plex."""

from abc import ABC, abstractmethod

import httpx

from app_logger import ModuleLogger
from core.base.database.models.mediaserver import MediaServerRead, MediaServerType

logger = ModuleLogger("MediaServerClient")


class BaseMediaServerClient(ABC):
    """Abstract base class for media server clients."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key

    @abstractmethod
    async def test_connection(self) -> str:
        """Test the connection to the media server. \n
        Returns:
            str: Success message with server version. \n
        Raises:
            ConnectionError: If connection fails.
        """
        pass

    @abstractmethod
    async def refresh_library(self, folder_path: str) -> bool:
        """Trigger a library scan for the specified folder. \n
        Args:
            folder_path (str): The folder path to scan. \n
        Returns:
            bool: True if the scan was triggered successfully.
        """
        pass


class EmbyClient(BaseMediaServerClient):
    """Client for communicating with Emby media server."""

    async def test_connection(self) -> str:
        """Test the connection to the Emby server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.url}/System/Info",
                    headers={"X-Emby-Token": self.api_key},
                )
                response.raise_for_status()
                data = response.json()
                version = data.get("Version", "Unknown")
                server_name = data.get("ServerName", "Emby")
                return f"{server_name} - Version: {version}"
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Connection to Emby timed out: {e}")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"Emby returned error: {e.response.status_code}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Emby: {e}")

    async def refresh_library(self, folder_path: str) -> bool:
        """Trigger a library scan on Emby for the specified folder."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.url}/Library/Refresh",
                    headers={"X-Emby-Token": self.api_key},
                )
                if response.status_code in [200, 204, 202]:
                    logger.debug(f"Emby library refresh triggered for: {folder_path}")
                    return True
                logger.warning(
                    f"Emby library refresh returned status: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to trigger Emby library refresh: {e}")
            return False


class JellyfinClient(BaseMediaServerClient):
    """Client for communicating with Jellyfin media server."""

    async def test_connection(self) -> str:
        """Test the connection to the Jellyfin server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.url}/System/Info",
                    headers={"Authorization": f'MediaBrowser Token="{self.api_key}"'},
                )
                response.raise_for_status()
                data = response.json()
                version = data.get("Version", "Unknown")
                server_name = data.get("ServerName", "Jellyfin")
                return f"{server_name} - Version: {version}"
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Connection to Jellyfin timed out: {e}")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(
                f"Jellyfin returned error: {e.response.status_code}"
            )
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Jellyfin: {e}")

    async def refresh_library(self, folder_path: str) -> bool:
        """Trigger a library scan on Jellyfin for the specified folder."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.url}/Library/Refresh",
                    headers={"Authorization": f'MediaBrowser Token="{self.api_key}"'},
                )
                if response.status_code in [200, 204, 202]:
                    logger.debug(
                        f"Jellyfin library refresh triggered for: {folder_path}"
                    )
                    return True
                logger.warning(
                    f"Jellyfin library refresh returned status: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to trigger Jellyfin library refresh: {e}")
            return False


class PlexClient(BaseMediaServerClient):
    """Client for communicating with Plex media server."""

    async def test_connection(self) -> str:
        """Test the connection to the Plex server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.url}/",
                    headers={
                        "X-Plex-Token": self.api_key,
                        "Accept": "application/json",
                    },
                )
                response.raise_for_status()
                data = response.json()
                media_container = data.get("MediaContainer", {})
                version = media_container.get("version", "Unknown")
                server_name = media_container.get("friendlyName", "Plex")
                return f"{server_name} - Version: {version}"
        except httpx.TimeoutException as e:
            raise ConnectionError(f"Connection to Plex timed out: {e}")
        except httpx.HTTPStatusError as e:
            raise ConnectionError(f"Plex returned error: {e.response.status_code}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Plex: {e}")

    async def _get_library_section_key(
        self, client: httpx.AsyncClient, folder_path: str
    ) -> str | None:
        """Get the library section key for a given folder path."""
        try:
            response = await client.get(
                f"{self.url}/library/sections",
                headers={
                    "X-Plex-Token": self.api_key,
                    "Accept": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()
            sections = data.get("MediaContainer", {}).get("Directory", [])
            for section in sections:
                locations = section.get("Location", [])
                for location in locations:
                    if folder_path.startswith(location.get("path", "")):
                        return section.get("key")
            return None
        except Exception as e:
            logger.warning(f"Failed to get Plex library sections: {e}")
            return None

    async def refresh_library(self, folder_path: str) -> bool:
        """Trigger a library scan on Plex for the specified folder."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Try to find the specific library section for this path
                section_key = await self._get_library_section_key(client, folder_path)

                if section_key:
                    # Refresh specific section
                    response = await client.get(
                        f"{self.url}/library/sections/{section_key}/refresh",
                        headers={"X-Plex-Token": self.api_key},
                    )
                else:
                    # Refresh all libraries
                    response = await client.get(
                        f"{self.url}/library/sections/all/refresh",
                        headers={"X-Plex-Token": self.api_key},
                    )

                if response.status_code in [200, 204, 202]:
                    logger.debug(f"Plex library refresh triggered for: {folder_path}")
                    return True
                logger.warning(
                    f"Plex library refresh returned status: {response.status_code}"
                )
                return False
        except Exception as e:
            logger.error(f"Failed to trigger Plex library refresh: {e}")
            return False


class MediaServerClient:
    """Factory class for creating media server clients."""

    @staticmethod
    def get_client(server: MediaServerRead) -> BaseMediaServerClient:
        """Get the appropriate client for the media server type. \n
        Args:
            server (MediaServerRead): The media server configuration. \n
        Returns:
            BaseMediaServerClient: The appropriate client instance. \n
        Raises:
            ValueError: If server type is not supported.
        """
        if server.server_type == MediaServerType.EMBY:
            return EmbyClient(server.url, server.api_key)
        elif server.server_type == MediaServerType.JELLYFIN:
            return JellyfinClient(server.url, server.api_key)
        elif server.server_type == MediaServerType.PLEX:
            return PlexClient(server.url, server.api_key)
        else:
            raise ValueError(f"Unsupported server type: {server.server_type}")

    @staticmethod
    async def test_connection(server: MediaServerRead) -> str:
        """Test connection to a media server. \n
        Args:
            server (MediaServerRead): The media server configuration. \n
        Returns:
            str: Success message with server information. \n
        Raises:
            ConnectionError: If connection fails.
        """
        client = MediaServerClient.get_client(server)
        return await client.test_connection()

    @staticmethod
    async def refresh_library(server: MediaServerRead, folder_path: str) -> bool:
        """Trigger a library refresh on a media server. \n
        Args:
            server (MediaServerRead): The media server configuration.
            folder_path (str): The folder path to scan. \n
        Returns:
            bool: True if the scan was triggered successfully.
        """
        client = MediaServerClient.get_client(server)
        return await client.refresh_library(folder_path)
