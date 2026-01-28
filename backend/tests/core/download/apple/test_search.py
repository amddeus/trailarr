"""Tests for Apple trailer search module."""

import pytest
from core.download.apple.search import (
    _normalize_title,
    _titles_match,
    _title_to_slug,
    _calculate_match_score,
    _slug_in_url,
    lookup_by_imdb_id,
    _find_content_url_in_data,
    search_web_for_apple_tv_url,
)


class TestSlugInUrl:
    """Tests for _slug_in_url function."""

    @pytest.mark.parametrize(
        "slug,url,expected",
        [
            # Valid matches - slug as a path segment
            ("test-movie", "/us/movie/test-movie/umc.123", True),
            ("predator-badlands", "/us/movie/predator-badlands/umc.cmc.5k", True),
            ("tron-ares", "https://tv.apple.com/us/movie/tron-ares/umc.cmc.abc", True),
            ("the-batman", "/us/movie/the-batman/", True),
            # End of URL (no trailing slash)
            ("test-movie", "/us/movie/test-movie", True),
            # False positives that should NOT match
            ("man", "/us/movie/superman/umc.123", False),  # "man" in "superman"
            ("man", "/us/movie/batman/umc.123", False),  # "man" in "batman"
            ("bad", "/us/movie/badlands/umc.123", False),  # "bad" in "badlands"
            ("land", "/us/movie/badlands/umc.123", False),  # "land" in "badlands"
            # Edge cases
            ("test", "/us/movie/testing/umc.123", False),  # "test" in "testing"
            ("", "/us/movie/anything/umc.123", False),  # Empty slug
        ],
    )
    def test_slug_in_url(self, slug, url, expected):
        """Test slug matching in URLs prevents false positives."""
        result = _slug_in_url(slug, url)
        assert result == expected, f"Expected {expected} for slug '{slug}' in URL '{url}'"


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
            # Additional tests for movies with issues
            ("Predator: Badlands", "predator-badlands"),
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
            # Predator should match Predator: Badlands
            ("Predator: Badlands", "Predator: Badlands", 200),
            ("Predator Badlands", "Predator: Badlands", 200),
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


class TestLookupByImdbId:
    """Tests for lookup_by_imdb_id function."""

    def test_lookup_empty_imdb_id(self):
        """Test that empty IMDB ID returns None."""
        result = lookup_by_imdb_id("", True)
        assert result is None
    
    def test_lookup_none_imdb_id(self):
        """Test that None IMDB ID returns None."""
        result = lookup_by_imdb_id(None, True)  # type: ignore
        assert result is None


class TestFindContentUrlInData:
    """Tests for _find_content_url_in_data function."""

    def test_find_url_in_nested_dict(self):
        """Test finding URL in nested dictionary structure."""
        data = {
            "level1": {
                "level2": {
                    "url": "/us/movie/test-movie/umc.cmc.12345"
                }
            }
        }
        result = _find_content_url_in_data(data, "test-movie", "movie")
        assert result == "https://tv.apple.com/us/movie/test-movie/umc.cmc.12345"

    def test_find_url_in_list(self):
        """Test finding URL in list of dictionaries."""
        data = [
            {"url": "/us/show/wrong-show/umc.cmc.99999"},
            {"canonicalUrl": "/us/movie/predator-badlands/umc.cmc.5k20n1ox51cwgge4sr476fr6p"},
        ]
        result = _find_content_url_in_data(data, "predator-badlands", "movie")
        assert result == "https://tv.apple.com/us/movie/predator-badlands/umc.cmc.5k20n1ox51cwgge4sr476fr6p"

    def test_no_match_found(self):
        """Test when no matching URL is found."""
        data = {"url": "/us/movie/other-movie/umc.cmc.12345"}
        result = _find_content_url_in_data(data, "test-movie", "movie")
        assert result is None

    def test_empty_data(self):
        """Test with empty data."""
        result = _find_content_url_in_data({}, "test-movie", "movie")
        assert result is None

    def test_url_without_content_id(self):
        """Test that URLs without content IDs are skipped."""
        data = {"url": "/us/movie/test-movie/"}
        result = _find_content_url_in_data(data, "test-movie", "movie")
        assert result is None  # No umc. in URL


class TestSearchWebForAppleTvUrl:
    """Tests for search_web_for_apple_tv_url function."""

    def test_empty_title_returns_none(self):
        """Test that empty title returns None quickly."""
        result = search_web_for_apple_tv_url("", 0, True)
        assert result is None

    def test_returns_none_on_http_error(self, mocker):
        """Test that HTTP errors are handled gracefully."""
        mock_get = mocker.patch("core.download.apple.search.requests.get")
        mock_get.return_value.status_code = 500

        result = search_web_for_apple_tv_url("Test Movie", 2024, True)
        assert result is None

    def test_extracts_apple_tv_url_from_search_results(self, mocker):
        """Test URL extraction from DuckDuckGo search results."""
        # Mock HTML response from DuckDuckGo with Apple TV URL
        html_response = '''
        <html>
        <body>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftv.apple.com%2Fus%2Fmovie%2Ftest-movie%2Fumc.cmc.abc123">
            Test Movie - Apple TV
        </a>
        </body>
        </html>
        '''
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_response

        mock_get = mocker.patch("core.download.apple.search.requests.get")
        mock_get.return_value = mock_response

        result = search_web_for_apple_tv_url("Test Movie", 2024, True)
        assert result == "https://tv.apple.com/us/movie/test-movie/umc.cmc.abc123"

    def test_filters_by_slug_to_avoid_wrong_movies(self, mocker):
        """Test that results not matching the slug are filtered out."""
        # Response contains URL for a different movie
        html_response = '''
        <html>
        <body>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftv.apple.com%2Fus%2Fmovie%2Fdifferent-movie%2Fumc.cmc.abc123">
            Different Movie - Apple TV
        </a>
        </body>
        </html>
        '''
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_response

        mock_get = mocker.patch("core.download.apple.search.requests.get")
        mock_get.return_value = mock_response

        result = search_web_for_apple_tv_url("Test Movie", 2024, True)
        assert result is None

    def test_handles_show_type_correctly(self, mocker):
        """Test that show type uses correct URL pattern."""
        html_response = '''
        <html>
        <body>
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Ftv.apple.com%2Fus%2Fshow%2Ftest-show%2Fumc.cmc.abc123">
            Test Show - Apple TV
        </a>
        </body>
        </html>
        '''
        mock_response = mocker.MagicMock()
        mock_response.status_code = 200
        mock_response.text = html_response

        mock_get = mocker.patch("core.download.apple.search.requests.get")
        mock_get.return_value = mock_response

        result = search_web_for_apple_tv_url("Test Show", 2024, is_movie=False)
        assert result == "https://tv.apple.com/us/show/test-show/umc.cmc.abc123"
