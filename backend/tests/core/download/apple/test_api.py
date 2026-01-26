"""Tests for Apple TV API module."""

import pytest
from core.download.apple.api import TrailerInfo


class TestTrailerInfo:
    """Tests for TrailerInfo class."""

    def test_trailer_info_creation(self):
        """Test creating TrailerInfo with all fields."""
        trailer = TrailerInfo(
            hls_url="https://example.com/trailer.m3u8",
            video_title="Official Trailer",
            content_title="Test Movie",
            release_date="2024-01-15",
            description="A test movie description",
            genres=["Action", "Adventure"],
            cover_url="https://example.com/cover.jpg",
            apple_id="umc.cmc.12345",
        )

        assert trailer.hls_url == "https://example.com/trailer.m3u8"
        assert trailer.video_title == "Official Trailer"
        assert trailer.content_title == "Test Movie"
        assert trailer.release_date == "2024-01-15"
        assert trailer.description == "A test movie description"
        assert trailer.genres == ["Action", "Adventure"]
        assert trailer.cover_url == "https://example.com/cover.jpg"
        assert trailer.apple_id == "umc.cmc.12345"

    def test_trailer_info_minimal(self):
        """Test creating TrailerInfo with minimal fields."""
        trailer = TrailerInfo(
            hls_url="https://example.com/trailer.m3u8",
            video_title="Trailer",
            content_title="Movie",
            release_date="2024-01-01",
        )

        assert trailer.hls_url == "https://example.com/trailer.m3u8"
        assert trailer.video_title == "Trailer"
        assert trailer.content_title == "Movie"
        assert trailer.genres == []
        assert trailer.cover_url is None
        assert trailer.apple_id is None

    def test_trailer_info_to_dict(self):
        """Test TrailerInfo.to_dict() method."""
        trailer = TrailerInfo(
            hls_url="https://example.com/trailer.m3u8",
            video_title="Official Trailer",
            content_title="Test Movie",
            release_date="2024-01-15",
            genres=["Action"],
            apple_id="test123",
        )

        result = trailer.to_dict()

        assert isinstance(result, dict)
        assert result["hls_url"] == "https://example.com/trailer.m3u8"
        assert result["video_title"] == "Official Trailer"
        assert result["content_title"] == "Test Movie"
        assert result["release_date"] == "2024-01-15"
        assert result["genres"] == ["Action"]
        assert result["apple_id"] == "test123"
