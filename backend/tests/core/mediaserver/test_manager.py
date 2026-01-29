"""Tests for MediaServer manager operations."""

import pytest
from core.base.database.models.mediaserver import (
    MediaServerCreate,
    MediaServerType,
    MediaServerUpdate,
)
import core.base.database.manager.mediaserver as mediaserver_manager
from exceptions import ItemNotFoundError


class TestMediaServerManager:
    """Tests for MediaServer manager CRUD operations."""

    def test_create_mediaserver(self):
        """Test creating a new media server."""
        mediaserver_data = MediaServerCreate(
            name="Test Emby",
            server_type=MediaServerType.EMBY,
            url="http://localhost:8096",
            api_key="test_api_key_12345",
            enabled=True,
        )
        result = mediaserver_manager.create(mediaserver_data)

        assert result.id is not None
        assert result.name == "Test Emby"
        assert result.server_type == MediaServerType.EMBY
        assert result.url == "http://localhost:8096"
        assert result.enabled is True

    def test_read_mediaserver(self):
        """Test reading a media server by ID."""
        mediaserver_data = MediaServerCreate(
            name="Test Jellyfin",
            server_type=MediaServerType.JELLYFIN,
            url="http://localhost:8097",
            api_key="jellyfin_api_key_12345",
            enabled=True,
        )
        created = mediaserver_manager.create(mediaserver_data)
        result = mediaserver_manager.read(created.id)

        assert result.id == created.id
        assert result.name == "Test Jellyfin"
        assert result.server_type == MediaServerType.JELLYFIN

    def test_read_nonexistent_mediaserver(self):
        """Test reading a media server that doesn't exist."""
        with pytest.raises(ItemNotFoundError):
            mediaserver_manager.read(99999)

    def test_read_all_mediaservers(self):
        """Test reading all media servers."""
        result = mediaserver_manager.read_all()
        assert isinstance(result, list)

    def test_read_all_enabled_mediaservers(self):
        """Test reading all enabled media servers."""
        # Create an enabled and a disabled server
        enabled_server = MediaServerCreate(
            name="Enabled Server",
            server_type=MediaServerType.PLEX,
            url="http://localhost:32400",
            api_key="plex_api_key_12345",
            enabled=True,
        )
        disabled_server = MediaServerCreate(
            name="Disabled Server",
            server_type=MediaServerType.PLEX,
            url="http://localhost:32401",
            api_key="plex_api_key_54321",
            enabled=False,
        )
        created_enabled = mediaserver_manager.create(enabled_server)
        created_disabled = mediaserver_manager.create(disabled_server)

        enabled_results = mediaserver_manager.read_all_enabled()

        enabled_ids = [s.id for s in enabled_results]
        assert created_enabled.id in enabled_ids
        assert created_disabled.id not in enabled_ids

    def test_update_mediaserver(self):
        """Test updating a media server."""
        mediaserver_data = MediaServerCreate(
            name="Original Name",
            server_type=MediaServerType.EMBY,
            url="http://localhost:8096",
            api_key="original_api_key",
            enabled=True,
        )
        created = mediaserver_manager.create(mediaserver_data)

        update_data = MediaServerUpdate(
            name="Updated Name",
            enabled=False,
        )
        result = mediaserver_manager.update(created.id, update_data)

        assert result.id == created.id
        assert result.name == "Updated Name"
        assert result.enabled is False
        assert result.server_type == MediaServerType.EMBY  # Unchanged

    def test_delete_mediaserver(self):
        """Test deleting a media server."""
        mediaserver_data = MediaServerCreate(
            name="To Be Deleted",
            server_type=MediaServerType.JELLYFIN,
            url="http://localhost:8097",
            api_key="delete_me_key",
            enabled=True,
        )
        created = mediaserver_manager.create(mediaserver_data)

        result = mediaserver_manager.delete(created.id)
        assert result is True

        with pytest.raises(ItemNotFoundError):
            mediaserver_manager.read(created.id)

    def test_exists_mediaserver(self):
        """Test checking if a media server exists."""
        mediaserver_data = MediaServerCreate(
            name="Exists Test",
            server_type=MediaServerType.PLEX,
            url="http://localhost:32400",
            api_key="exists_test_key",
            enabled=True,
        )
        created = mediaserver_manager.create(mediaserver_data)

        assert mediaserver_manager.exists(created.id) is True
        assert mediaserver_manager.exists(99999) is False
