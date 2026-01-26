"""Apple TV trailer search functionality."""

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urlparse

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


def _titles_match(title1: str, title2: str, strict: bool = False) -> bool:
    """Check if two titles match (fuzzy comparison)."""
    norm1 = _normalize_title(title1)
    norm2 = _normalize_title(title2)

    # Exact match
    if norm1 == norm2:
        return True

    # Check if one contains the other (for titles with subtitles)
    if norm1 in norm2 or norm2 in norm1:
        return True

    if strict:
        return False

    # Check word overlap (at least 60% of words match for non-strict)
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    if not words1 or not words2:
        return False

    overlap = len(words1 & words2)
    min_len = min(len(words1), len(words2))
    if min_len > 0 and overlap / min_len >= 0.6:
        return True

    return False


def _calculate_match_score(
    result_title: str,
    search_title: str,
    result_year: int,
    search_year: int,
    has_preview: bool = False,
) -> int:
    """Calculate a match score between search and result.
    
    Returns a score where higher is better. A score of 0 or negative means
    the titles don't match at all.
    """
    score = 0
    norm_result = _normalize_title(result_title)
    norm_search = _normalize_title(search_title)

    # Exact match gets highest score
    if norm_result == norm_search:
        score += 200

    # One contains the other (for titles with subtitles)
    elif norm_result in norm_search or norm_search in norm_result:
        score += 150

    # Word overlap scoring - only if there's significant overlap
    else:
        words_search = set(norm_search.split())
        words_result = set(norm_result.split())
        if words_search and words_result:
            overlap = words_search & words_result
            # Must have at least 50% word overlap to be considered
            search_overlap_pct = len(overlap) / len(words_search) if words_search else 0
            result_overlap_pct = len(overlap) / len(words_result) if words_result else 0
            
            # Take the higher percentage (so "TRON: Ares" matches "TRON: Ares 2025")
            overlap_pct = max(search_overlap_pct, result_overlap_pct)
            
            if overlap_pct >= 0.5:
                score += int(overlap_pct * 100)
            # else: score stays 0, meaning no title match

    # Year match scoring - only add bonus, not as primary match
    if search_year > 0 and result_year > 0:
        year_diff = abs(search_year - result_year)
        if year_diff == 0:
            score += 30
        elif year_diff == 1:
            score += 15
        elif year_diff <= 2:
            score += 5
        elif year_diff > 5:
            score -= 50  # Heavy penalty for large year differences

    # Prefer results with trailers
    if has_preview:
        score += 5

    return score


def search_apple_tv_api(
    title: str, year: int = 0, is_movie: bool = True
) -> list[dict[str, Any]]:
    """Search Apple TV using their internal API."""
    logger.debug(f"Searching Apple TV API for: {title} ({year})")

    search_term = title
    if year:
        search_term = f"{title} {year}"

    # Apple TV's internal search API
    api_url = "https://tv.apple.com/api/uts/v3/canvases/search"
    params = {
        "caller": "web",
        "locale": "en-US",
        "pfm": "appletv",
        "sf": "143441",
        "term": search_term,
        "utscf": "OjAAAAAAAAA~",
        "utsk": "6e3013c6d6fae3c2::::::235656c069bb0efb",
        "v": "72",
    }

    try:
        response = requests.get(
            api_url, params=params, headers=HEADERS, timeout=30
        )
        if response.status_code != 200:
            # Try without SSL verification
            response = requests.get(
                api_url,
                params=params,
                headers=HEADERS,
                timeout=30,
                verify=False,
            )
        if response.status_code != 200:
            logger.debug(f"Apple TV API search returned {response.status_code}")
            return []
        data = response.json()
    except Exception as e:
        logger.debug(f"Apple TV API search failed: {e}")
        return []

    # Extract content items from search results
    results: list[dict[str, Any]] = []
    target_type = "Movie" if is_movie else "Show"

    def extract_items(obj: Any) -> None:
        if isinstance(obj, dict):
            # Check if this is a content item with required fields
            item_type = obj.get("type", "")
            item_id = obj.get("id", "")
            item_title = obj.get("title", "")
            item_url = obj.get("url", "") or obj.get("canonicalUrl", "")

            if item_id and item_title:
                # Check if type matches what we're looking for
                if target_type.lower() in item_type.lower() or not item_type:
                    result_year = 0
                    release_date = obj.get("releaseDate", "")
                    if release_date:
                        try:
                            if isinstance(release_date, (int, float)):
                                result_year = datetime.utcfromtimestamp(
                                    release_date / 1000
                                ).year
                            else:
                                result_year = int(str(release_date)[:4])
                        except (ValueError, TypeError):
                            pass

                    score = _calculate_match_score(
                        item_title, title, result_year, year
                    )
                    # Require at least 50 points to ensure actual title match
                    if score >= 50:
                        results.append(
                            {
                                "id": item_id,
                                "title": item_title,
                                "url": item_url,
                                "type": item_type,
                                "year": result_year,
                                "score": score,
                            }
                        )

            # Recurse into nested structures
            for v in obj.values():
                extract_items(v)
        elif isinstance(obj, list):
            for item in obj:
                extract_items(item)

    extract_items(data)

    # Sort by score and remove duplicates
    seen_ids = set()
    unique_results = []
    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            unique_results.append(r)

    return unique_results


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
        if response.status_code != 200:
            response = requests.get(url, timeout=30, verify=False)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.debug(f"iTunes search failed: {e}")
        return []

    results = data.get("results", [])
    if not results:
        logger.debug(f"No iTunes results found for: {title}")
        return []

    # Score and filter results
    scored_results: list[tuple[int, dict[str, Any]]] = []

    for result in results:
        track_name = result.get("trackName", "") or result.get(
            "collectionName", ""
        )
        release_date = result.get("releaseDate", "")
        result_year = 0

        if release_date:
            try:
                result_year = int(release_date[:4])
            except (ValueError, TypeError):
                pass

        score = _calculate_match_score(
            track_name,
            title,
            result_year,
            year,
            has_preview=bool(result.get("previewUrl")),
        )

        # Require at least 50 points to ensure actual title match
        if score >= 50:
            scored_results.append((score, result))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in scored_results]


def search_apple_tv_web(
    title: str, year: int = 0, is_movie: bool = True
) -> str | None:
    """Search Apple TV website for content URL."""
    logger.debug(f"Searching Apple TV web for: {title} ({year})")

    search_term = quote_plus(f"{title} {year}" if year else title)
    search_url = f"https://tv.apple.com/us/search?term={search_term}"

    try:
        response = requests.get(search_url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            response = requests.get(
                search_url, headers=HEADERS, timeout=30, verify=False
            )
        if response.status_code != 200:
            logger.debug(f"Apple TV web search returned {response.status_code}")
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
        media_type = "movie" if is_movie else "show"
        links = soup.find_all("a", href=True)
        for link in links:
            href = link["href"]
            if f"/us/{media_type}/" in href:
                if not href.startswith("http"):
                    href = f"https://tv.apple.com{href}"
                return href

    except Exception as e:
        logger.debug(f"Apple TV web search failed: {e}")

    return None


def _extract_content_url_from_search(
    data: Any, title: str, year: int, is_movie: bool
) -> str | None:
    """Extract content URL from Apple TV search results JSON."""
    candidates: list[tuple[int, str]] = []

    def search_recursive(obj: Any) -> None:
        if isinstance(obj, dict):
            item_title = obj.get("title", "")
            item_url = obj.get("url", "") or obj.get("canonicalUrl", "")
            item_type = obj.get("type", "").lower()
            item_id = obj.get("id", "")

            if item_title and (item_url or item_id):
                # Check content type matches
                type_matches = False
                if is_movie and ("movie" in item_type or not item_type):
                    type_matches = True
                elif not is_movie and ("show" in item_type or not item_type):
                    type_matches = True

                if type_matches:
                    result_year = 0
                    release_date = obj.get("releaseDate", "")
                    if release_date:
                        try:
                            if isinstance(release_date, (int, float)):
                                result_year = datetime.utcfromtimestamp(
                                    release_date / 1000
                                ).year
                            else:
                                result_year = int(str(release_date)[:4])
                        except (ValueError, TypeError):
                            pass

                    score = _calculate_match_score(
                        item_title, title, result_year, year
                    )
                    # Require at least 50 points to ensure actual title match
                    if score >= 50:
                        url = item_url
                        if not url and item_id:
                            media = "movie" if is_movie else "show"
                            url = f"https://tv.apple.com/us/{media}/-/{item_id}"
                        if url:
                            candidates.append((score, url))

            for v in obj.values():
                search_recursive(v)
        elif isinstance(obj, list):
            for item in obj:
                search_recursive(item)

    search_recursive(data)

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    return None


def search_for_trailer(
    media: MediaRead,
    exclude: list[str] | None = None,
) -> TrailerInfo | None:
    """Search for a trailer for the given media item.

    Uses multiple search strategies:
    1. Apple TV internal search API
    2. Apple TV web search with embedded JSON
    3. iTunes API fallback
    """
    logger.info(f"Searching Apple TV for trailer for '{media.title}'...")

    if not exclude:
        exclude = []

    content_url: str | None = None

    # Strategy 1: Try Apple TV internal search API first
    api_results = search_apple_tv_api(media.title, media.year, media.is_movie)
    if api_results:
        best_result = api_results[0]
        content_url = best_result.get("url")
        if not content_url and best_result.get("id"):
            media_type = "movie" if media.is_movie else "show"
            content_url = (
                f"https://tv.apple.com/us/{media_type}/-/{best_result['id']}"
            )
        logger.debug(f"Found via API search: {content_url}")

    # Strategy 2: Try Apple TV web search
    if not content_url:
        content_url = search_apple_tv_web(
            media.title, media.year, media.is_movie
        )
        if content_url:
            logger.debug(f"Found via web search: {content_url}")

    # Strategy 3: Try iTunes API fallback
    if not content_url:
        itunes_results = search_apple_itunes(
            media.title, media.year, media.is_movie
        )

        for result in itunes_results:
            track_id = result.get("trackId") or result.get("collectionId")
            track_url = result.get("trackViewUrl", "")

            # Try to extract Apple TV URL from iTunes URL
            # Validate that the URL is actually from Apple's domains
            if track_url:
                try:
                    parsed = urlparse(track_url)
                    # Check that domain ends with apple.com (not a subdomain attack)
                    if parsed.netloc.endswith(".apple.com") or parsed.netloc == "apple.com":
                        if "/movie/" in track_url or "/tv-season/" in track_url:
                            content_url = track_url.replace(
                                "itunes.apple.com", "tv.apple.com"
                            )
                            logger.debug(f"Found via iTunes: {content_url}")
                            break
                except Exception:
                    pass

            # Last resort: try to construct a URL from track ID
            if track_id:
                media_type = "movie" if media.is_movie else "show"
                # Try to lookup by ID directly
                test_url = f"https://tv.apple.com/us/{media_type}/-/{track_id}"
                content_url = test_url
                logger.debug(f"Constructed URL from track ID: {content_url}")
                break

    if not content_url:
        logger.warning(
            f"No Apple TV content found for '{media.title}' [{media.id}]"
        )
        return None

    logger.debug(f"Attempting to fetch trailer from: {content_url}")

    # Fetch trailers from the content URL
    try:
        atvp = AppleTVPlus()
        trailers = atvp.get_trailers(content_url, default_only=True)

        if trailers:
            trailer = trailers[0]
            
            # CRITICAL: Validate that the returned content matches what we searched for
            # This prevents downloading trailers for wrong movies
            content_score = _calculate_match_score(
                trailer.content_title,
                media.title,
                0,  # Don't use year for this check
                0,
            )
            if content_score < 50:
                logger.warning(
                    f"Trailer content title '{trailer.content_title}' does not match "
                    f"search title '{media.title}' (score: {content_score}). Skipping."
                )
                return None
            
            # Check if excluded
            if trailer.apple_id and trailer.apple_id in exclude:
                logger.debug(f"Trailer {trailer.apple_id} is in exclude list")
                if len(trailers) > 1:
                    for t in trailers[1:]:
                        if t.apple_id not in exclude:
                            # Also validate this alternate trailer
                            alt_score = _calculate_match_score(
                                t.content_title, media.title, 0, 0
                            )
                            if alt_score >= 50:
                                return t
                return None

            logger.info(
                f"Found trailer for '{media.title}': {trailer.video_title}"
            )
            return trailer
        else:
            logger.debug(f"No trailers returned from URL: {content_url}")

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
