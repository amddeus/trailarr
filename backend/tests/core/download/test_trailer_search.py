import pytest
from core.download.trailers.utils import extract_youtube_id


@pytest.mark.parametrize(
    "url,expected",
    [
        # Standard YouTube watch URLs
        ("https://www.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
        ("https://youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
        ("https://m.youtube.com/watch?v=abcdefghijk", "abcdefghijk"),
        (
            "https://www.youtube.com/watch?v=abcdefghijk&feature=related",
            "abcdefghijk",
        ),
        # Short youtu.be URLs
        ("https://youtu.be/abcdefghijk", "abcdefghijk"),
        # Embed URLs
        ("https://www.youtube.com/embed/abcdefghijk", "abcdefghijk"),
        # /v/ URLs
        ("https://www.youtube.com/v/abcdefghijk", "abcdefghijk"),
        # /u/1/ URLs
        ("https://www.youtube.com/u/1/abcdefghijk", "abcdefghijk"),
        # With additional parameters
        (
            "https://www.youtube.com/watch?v=abcdefghijk&list=PL1234567890",
            "abcdefghijk",
        ),
        # Invalid: wrong length
        ("https://www.youtube.com/watch?v=abcde", None),
        ("https://youtu.be/abcde", None),
        # Invalid: no video id
        ("https://www.youtube.com/", None),
        ("https://youtu.be/", None),
        # Invalid: not a YouTube URL
        ("https://vimeo.com/123456789", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_youtube_id(url, expected):
    if url is None:
        result = extract_youtube_id("")
    else:
        result = extract_youtube_id(url)
    assert result == expected
