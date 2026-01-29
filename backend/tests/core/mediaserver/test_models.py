"""Tests for MediaServer models."""

from datetime import datetime, timezone
import pytest
from core.base.database.models.mediaserver import (
    MediaServer,
    MediaServerBase,
    MediaServerCreate,
    MediaServerRead,
    MediaServerType,
    MediaServerUpdate,
)


class TestMediaServerType:
    """Tests for MediaServerType enum."""

    def test_mediaserver_types(self):
        """Test all media server types are available."""
        assert MediaServerType.EMBY.value == "emby"
        assert MediaServerType.JELLYFIN.value == "jellyfin"
        assert MediaServerType.PLEX.value == "plex"


class TestMediaServerCreate:
    """Tests for MediaServerCreate model."""

    def test_create_with_defaults(self):
        """Test creating a media server with default values."""
        server = MediaServerCreate(
            name="Test Server",
            server_type=MediaServerType.EMBY,
            url="http://localhost:8096",
            api_key="test_api_key",
        )
        assert server.name == "Test Server"
        assert server.server_type == MediaServerType.EMBY
        assert server.url == "http://localhost:8096"
        assert server.api_key == "test_api_key"
        assert server.enabled is True

    def test_create_disabled(self):
        """Test creating a disabled media server."""
        server = MediaServerCreate(
            name="Disabled Server",
            server_type=MediaServerType.JELLYFIN,
            url="http://localhost:8097",
            api_key="test_api_key",
            enabled=False,
        )
        assert server.enabled is False


class TestMediaServerUpdate:
    """Tests for MediaServerUpdate model."""

    def test_update_partial(self):
        """Test partial update with some fields."""
        update = MediaServerUpdate(name="Updated Name")
        assert update.name == "Updated Name"
        assert update.url is None
        assert update.api_key is None

    def test_update_all_fields(self):
        """Test update with all fields."""
        update = MediaServerUpdate(
            name="New Name",
            server_type=MediaServerType.PLEX,
            url="http://newurl:32400",
            api_key="new_api_key",
            enabled=False,
        )
        assert update.name == "New Name"
        assert update.server_type == MediaServerType.PLEX
        assert update.url == "http://newurl:32400"
        assert update.api_key == "new_api_key"
        assert update.enabled is False


class TestMediaServerRead:
    """Tests for MediaServerRead model."""

    def test_read_model(self):
        """Test the MediaServerRead model."""
        read_data = {
            "id": 1,
            "name": "Test Server",
            "server_type": MediaServerType.EMBY,
            "url": "http://localhost:8096",
            "api_key": "test_key",
            "enabled": True,
            "added_at": datetime.now(timezone.utc),
        }
        server = MediaServerRead.model_validate(read_data)
        assert server.id == 1
        assert server.name == "Test Server"
        assert server.added_at is not None

    def test_timezone_correction(self):
        """Test that naive datetimes are corrected to UTC."""
        read_data = {
            "id": 1,
            "name": "Test Server",
            "server_type": MediaServerType.JELLYFIN,
            "url": "http://localhost:8097",
            "api_key": "test_key",
            "enabled": True,
            "added_at": datetime.now(),  # Naive datetime
        }
        server = MediaServerRead.model_validate(read_data)
        assert server.added_at.tzinfo is not None
