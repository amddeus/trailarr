"""Tests for Apple trailer search module."""

import pytest
from core.download.apple.search import (
    _normalize_title,
    _titles_match,
)


class TestNormalizeTitle:
    """Tests for _normalize_title function."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Test Movie", "test movie"),
            ("The Dark Knight", "the dark knight"),
            ("Spider-Man: No Way Home", "spiderman no way home"),
            ("  Extra   Spaces  ", "extra spaces"),
            ("Movie: Subtitle!", "movie subtitle"),
            ("Test's Movie", "tests movie"),
            ("123 Movie", "123 movie"),
            ("", ""),
        ],
    )
    def test_normalize_title(self, title, expected):
        """Test title normalization."""
        result = _normalize_title(title)
        assert result == expected


class TestTitlesMatch:
    """Tests for _titles_match function."""

    @pytest.mark.parametrize(
        "title1,title2,expected",
        [
            # Exact matches
            ("Test Movie", "Test Movie", True),
            ("Test Movie", "test movie", True),
            # Substring matches
            ("Test Movie", "Test Movie: Extended Edition", True),
            ("The Matrix", "The Matrix Reloaded", True),
            # No match
            ("Test Movie", "Different Film", False),
            ("Spider-Man", "Batman", False),
            # Empty strings - both empty match
            ("", "", True),
            # One empty, one not - substring match ("test" in "")
            ("Test", "", True),  # "" is in "test" so matches
        ],
    )
    def test_titles_match(self, title1, title2, expected):
        """Test title matching."""
        result = _titles_match(title1, title2)
        assert result == expected
