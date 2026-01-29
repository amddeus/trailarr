"""Tests for trailer download module."""

import pytest
from unittest.mock import patch, MagicMock


class TestGetTrailerFromManualId:
    """Tests for _get_trailer_from_manual_id function."""

    @pytest.mark.parametrize(
        "apple_id,media_title,is_movie,expected_url",
        [
            # TV show with umc ID - should use title slug
            (
                "umc.cmc.4imxd4eidvdbx873e9jetgkik",
                "A Knight of the Seven Kingdoms",
                False,
                "https://tv.apple.com/us/show/a-knight-of-the-seven-kingdoms/umc.cmc.4imxd4eidvdbx873e9jetgkik",
            ),
            # Movie with umc ID - should use title slug
            (
                "umc.cmc.abc123",
                "TRON: Ares",
                True,
                "https://tv.apple.com/us/movie/tron-ares/umc.cmc.abc123",
            ),
            # TV show with special characters in title
            (
                "umc.cmc.test123",
                "The Batman: Year One",
                False,
                "https://tv.apple.com/us/show/the-batman-year-one/umc.cmc.test123",
            ),
        ],
    )
    def test_constructs_url_with_title_slug(
        self, apple_id, media_title, is_movie, expected_url
    ):
        """Test that URL is constructed with the media title as a slug.
        
        This ensures TV shows and movies use proper slugs like
        'a-knight-of-the-seven-kingdoms' instead of just '-'.
        """
        with patch(
            "core.download.trailer.AppleTVPlus"
        ) as mock_apple:
            # Set up the mock to capture the URL passed to get_trailers
            mock_instance = MagicMock()
            mock_apple.return_value = mock_instance
            mock_instance.get_trailers.return_value = []

            from core.download.trailer import _get_trailer_from_manual_id

            _get_trailer_from_manual_id(apple_id, media_title, is_movie)

            # Verify the URL passed to get_trailers
            mock_instance.get_trailers.assert_called_once()
            actual_url = mock_instance.get_trailers.call_args[0][0]
            assert (
                actual_url == expected_url
            ), f"Expected URL '{expected_url}' but got '{actual_url}'"

    def test_full_url_is_used_as_is(self):
        """Test that a full URL is passed through without modification."""
        full_url = "https://tv.apple.com/us/show/a-knight-of-the-seven-kingdoms/umc.cmc.4imxd4eidvdbx873e9jetgkik"

        with patch(
            "core.download.trailer.AppleTVPlus"
        ) as mock_apple:
            mock_instance = MagicMock()
            mock_apple.return_value = mock_instance
            mock_instance.get_trailers.return_value = []

            from core.download.trailer import _get_trailer_from_manual_id

            _get_trailer_from_manual_id(full_url, "A Knight of the Seven Kingdoms", False)

            mock_instance.get_trailers.assert_called_once()
            actual_url = mock_instance.get_trailers.call_args[0][0]
            assert actual_url == full_url

    def test_returns_none_for_empty_apple_id(self):
        """Test that empty apple_id returns None without API call."""
        from core.download.trailer import _get_trailer_from_manual_id

        result = _get_trailer_from_manual_id("", "Test Title", True)
        assert result is None

    def test_returns_none_for_invalid_id_format(self):
        """Test that invalid ID format returns None."""
        from core.download.trailer import _get_trailer_from_manual_id

        result = _get_trailer_from_manual_id("invalid-format", "Test Title", True)
        assert result is None
