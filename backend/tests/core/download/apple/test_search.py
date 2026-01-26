"""Tests for Apple trailer search module."""

import pytest
from core.download.apple.search import (
    _normalize_title,
    _titles_match,
    _title_to_slug,
    _calculate_match_score,
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


class TestTitleToSlug:
    """Tests for _title_to_slug function."""

    @pytest.mark.parametrize(
        "title,expected",
        [
            ("TRON: Ares", "tron-ares"),
            ("Spider-Man: No Way Home", "spider-man-no-way-home"),
            ("The Batman", "the-batman"),
            ("Avengers: Endgame", "avengers-endgame"),
            ("Fast & Furious 9", "fast-furious-9"),
            ("Test Movie", "test-movie"),
            ("A Movie: With Subtitle", "a-movie-with-subtitle"),
            ("Movie's Name", "movie-s-name"),  # Apostrophe becomes space/hyphen
            ("", ""),
        ],
    )
    def test_title_to_slug(self, title, expected):
        """Test title to slug conversion."""
        result = _title_to_slug(title)
        assert result == expected


class TestCalculateMatchScore:
    """Tests for _calculate_match_score function."""

    @pytest.mark.parametrize(
        "result_title,search_title,min_expected_score",
        [
            # Exact matches should score high
            ("TRON: Ares", "TRON: Ares", 200),
            ("The Batman", "The Batman", 200),
            # Normalized matches should also score high
            ("Tron Ares", "TRON: Ares", 200),
            # Mismatches should score 0
            ("The Gorge", "TRON: Ares", 0),
            ("Spider-Man", "Batman", 0),
            ("Completely Different", "Test Movie", 0),
        ],
    )
    def test_calculate_match_score(
        self, result_title, search_title, min_expected_score
    ):
        """Test match score calculation."""
        score = _calculate_match_score(result_title, search_title, 0, 0)
        if min_expected_score == 0:
            assert score == 0, f"Expected 0 but got {score}"
        else:
            assert (
                score >= min_expected_score
            ), f"Expected at least {min_expected_score} but got {score}"


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
            # One empty - empty string is always a substring of any string
            ("Test", "", True),
        ],
    )
    def test_titles_match(self, title1, title2, expected):
        """Test title matching."""
        result = _titles_match(title1, title2)
        assert result == expected
