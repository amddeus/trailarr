"""Apple TV trailer search functionality."""

import json
import re
from typing import Any
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

from app_logger import ModuleLogger
from core.base.database.models.media import MediaRead
from core.download.apple.api import AppleTVPlus, TrailerInfo, HEADERS

logger = ModuleLogger("AppleTrailerSearch")


def _normalize_title(title: str) -> str:
    """Normalize a title for comparison."""
    title = title.lower()
    # Remove special characters and extra spaces
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _titles_match(title1: str, title2: str) -> bool:
    """Check if two titles match (fuzzy comparison)."""
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)

    # Exact match
    if norm1 == norm2:
        return True

    # Check if one contains the other (for titles with subtitles)
    if norm1 in norm2 or norm2 in norm1:
        return True

    # Check word overlap (at least 70% of words match)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if not words1 or not words2:
        return False

    overlap = len(words1 & words2)
    min_len = min(len(words1), len(words2))
    if min_len > 0 and overlap / min_len >= 0.7:
        return True

    return False


def search_apple_itunes(
    title: str, year: int = 0, is_movie: bool = True
) -> list[dict[str, Any]]:
    """Search iTunes API for content matching title and year."""
    logger.debug(f"Searching iTunes for: {title} ({year})")

    media_type = "movie" if is_movie else "tvShow"
    search_term = quote_plus(title)

    url = (
        f"https://itunes.apple.com/search?"
        f"term={search_term}&media={media_type}&entity={media_type}&limit=25"
    )

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"iTunes search failed: {e}")
        return []

    results = data.get("results", [])
    if not results:
        logger.debug(f"No results found for: {title}")
        return []

    # Filter and score results
    scored_results: list[tuple[int, dict[str, Any]]] = []

    for result in results:
        track_name = result.get("trackName", "") or result.get(
            "collectionName", ""
        )
        release_date = result.get("releaseDate", "")
        release_year = 0

        if release_date:
            try:
                release_year = int(release_date[:4])
            except ValueError:
                pass

        # Calculate match score
        score = 0

        # Title match
        if _titles_match(title, track_name):
            score += 100

        # Year match (allow 1 year difference)
        if year > 0 and release_year > 0:
            year_diff = abs(year - release_year)
            if year_diff == 0:
                score += 50
            elif year_diff == 1:
                score += 25
            elif year_diff <= 2:
                score += 10

        # Prefer results with trailers
        if result.get("previewUrl"):
            score += 20

        if score > 0:
            scored_results.append((score, result))

    # Sort by score descending
    scored_results.sort(key=lambda x: x[0], reverse=True)

    return [r[1] for r in scored_results]


def search_apple_tv_web(
    title: str, year: int = 0, is_movie: bool = True
) -> str | None:
    """Search Apple TV website for content URL."""
    logger.debug(f"Searching Apple TV for: {title} ({year})")

    media_type = "movies" if is_movie else "tv-shows"
    search_term = quote_plus(f"{title} {year}" if year else title)

    search_url = f"https://tv.apple.com/us/search?term={search_term}"

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            logger.debug(
                f"Apple TV search returned status {response.status_code}"
            )
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Look for embedded JSON data with search results
        script_tag = soup.find(
            "script",
            attrs={"type": "application/json", "id": "serialized-server-data"},
        )

        if script_tag:
            try:
                data = json.loads(script_tag.text)
                content_url = _extract_content_url_from_search(
                    data, title, year, is_movie
                )
                if content_url:
                    return content_url
            except json.JSONDecodeError:
                pass

        # Fallback: try to find direct links in the page
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if (
                f"/us/{media_type[:-1]}/" in href
                or f"/us/movie/" in href
                or f"/us/show/" in href
            ):
                # Construct full URL if relative
                if not href.startswith("http"):
                    href = f"https://tv.apple.com{href}"
                return href

    except Exception as e:
        logger.error(f"Apple TV web search failed: {e}")

    return None


def _extract_content_url_from_search(
    data: Any, title: str, year: int, is_movie: bool
) -> str | None:
    """Extract content URL from Apple TV search results JSON."""

    def search_recursive(obj: Any) -> str | None:
        if isinstance(obj, dict):
            # Check if this is a content item
            item_title = obj.get("title", "")
            item_url = obj.get("url", "") or obj.get("canonicalUrl", "")

            if item_title and item_url and _titles_match(title, item_title):
                # Check content type
                content_type = obj.get("type", "").lower()
                if is_movie and "movie" in content_type:
                    return item_url
                elif not is_movie and "show" in content_type:
                    return item_url
                elif not content_type:  # Unknown type, still return
                    return item_url

            # Recurse into nested structures
            for v in obj.values():
                result = search_recursive(v)
                if result:
                    return result

        elif isinstance(obj, list):
            for item in obj:
                result = search_recursive(item)
                if result:
                    return result

        return None

    return search_recursive(data)


def search_for_trailer(
    media: MediaRead,
    exclude: list[str] | None = None,
) -> TrailerInfo | None:
    """Search for a trailer for the given media item."""
    logger.info(f"Searching Apple TV for trailer for '{media.title}'...")

    if not exclude:
        exclude = []

    # First, try to find the content on Apple TV
    content_url = search_apple_tv_web(
        media.title, media.year, media.is_movie
    )

    if not content_url:
        # Fallback: Try iTunes API to get Apple ID and construct URL
        itunes_results = search_apple_itunes(
            media.title, media.year, media.is_movie
        )

        if itunes_results:
            # Get the Apple ID from iTunes result
            for result in itunes_results:
                track_id = result.get("trackId") or result.get("collectionId")
                if track_id:
                    # Construct Apple TV URL from track ID
                    media_type = "movie" if media.is_movie else "show"
                    content_url = (
                        f"https://tv.apple.com/us/{media_type}/"
                        f"{_normalize_title(media.title)}/umc.cmc.{track_id}"
                    )
                    break

    if not content_url:
        logger.warning(
            f"No Apple TV content found for '{media.title}' [{media.id}]"
        )
        return None

    logger.debug(f"Found Apple TV URL: {content_url}")

    # Fetch trailers from the content URL
    try:
        atvp = AppleTVPlus()
        trailers = atvp.get_trailers(content_url, default_only=True)

        if trailers:
            trailer = trailers[0]
            # Check if excluded
            if trailer.apple_id and trailer.apple_id in exclude:
                logger.debug(
                    f"Trailer {trailer.apple_id} is in exclude list"
                )
                if len(trailers) > 1:
                    for t in trailers[1:]:
                        if t.apple_id not in exclude:
                            return t
                return None

            logger.info(
                f"Found trailer for '{media.title}': {trailer.video_title}"
            )
            return trailer

    except Exception as e:
        logger.error(f"Failed to get trailer from Apple TV: {e}")

    return None


def get_trailer_by_url(url: str) -> TrailerInfo | None:
    """Get trailer information directly from an Apple TV URL."""
    try:
        atvp = AppleTVPlus()
        trailers = atvp.get_trailers(url, default_only=True)
        return trailers[0] if trailers else None
    except Exception as e:
        logger.error(f"Failed to get trailer from URL: {e}")
        return None
