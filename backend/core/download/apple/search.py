"""Apple TV trailer search functionality."""

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus, urlparse
from unicodedata import normalize

import requests
from bs4 import BeautifulSoup

from app_logger import ModuleLogger
from core.base.database.models.media import MediaRead
from core.download.apple.api import AppleTVPlus, TrailerInfo, HEADERS

logger = ModuleLogger("AppleTrailerSearch")

# Minimum score required for a title match to be considered valid
# This ensures we don't download trailers for wrong movies
MINIMUM_TITLE_MATCH_SCORE = 50


def _slug_in_url(slug: str, url: str) -> bool:
    """Check if a slug appears as a complete path segment in a URL.
    
    This prevents false positives like "man" matching "superman" or "batman".
    The slug must be surrounded by "/" characters to be a valid match.
    """
    url_lower = url.lower()
    # Check for slug as a path segment (surrounded by slashes or end of URL)
    if f"/{slug}/" in url_lower:
        return True
    if url_lower.endswith(f"/{slug}"):
        return True
    return False


def _title_to_slug(title: str) -> str:
    """Convert a title to a URL-friendly slug like Apple TV uses.
    
    Examples:
        "TRON: Ares" -> "tron-ares"
        "Spider-Man: No Way Home" -> "spider-man-no-way-home"
        "The Batman" -> "the-batman"
    """
    # Normalize unicode characters
    slug = normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    # Convert to lowercase
    slug = slug.lower()
    # Replace special chars with spaces (except hyphens)
    slug = re.sub(r"[^\w\s-]", " ", slug)
    # Replace whitespace with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Remove duplicate hyphens
    slug = re.sub(r"-+", "-", slug)
    # Strip leading/trailing hyphens
    slug = slug.strip("-")
    return slug


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
                    if score >= MINIMUM_TITLE_MATCH_SCORE:
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
        if score >= MINIMUM_TITLE_MATCH_SCORE:
            scored_results.append((score, result))

    scored_results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in scored_results]


def lookup_by_imdb_id(imdb_id: str, is_movie: bool = True) -> str | None:
    """Try to find Apple TV content URL using IMDB ID.
    
    Searches Apple TV using the IMDB ID as a search term. When IMDB IDs are
    available, this can help find content more reliably than title-based search.
    """
    if not imdb_id:
        return None
    
    logger.debug(f"Looking up Apple TV content by IMDB ID: {imdb_id}")
    
    search_url = f"https://tv.apple.com/us/search?term={imdb_id}"
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            logger.warning("SSL verification failed, retrying without verification")
            response = requests.get(
                search_url, headers=HEADERS, timeout=30, verify=False
            )
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            media_type = "movie" if is_movie else "show"
            
            # Look for embedded JSON data
            script_tag = soup.find(
                "script",
                attrs={"type": "application/json", "id": "serialized-server-data"},
            )
            
            if script_tag:
                try:
                    data = json.loads(script_tag.text)
                    # Use helper to find first content URL (no slug filter for IMDB search)
                    url = _find_first_content_url(data, media_type)
                    if url:
                        logger.debug(f"Found URL via IMDB search: {url}")
                        return url
                except json.JSONDecodeError:
                    pass
            
            # Also check for direct links in the page
            links = soup.find_all("a", href=True)
            for link in links:
                href = link.get("href", "")
                if f"/us/{media_type}/" in href and "umc." in href:
                    if not href.startswith("http"):
                        href = f"https://tv.apple.com{href}"
                    logger.debug(f"Found direct link via IMDB search: {href}")
                    return href
    
    except Exception as e:
        logger.debug(f"IMDB lookup failed: {e}")
    
    return None


def _find_first_content_url(data: Any, media_type: str) -> str | None:
    """Find the first content URL in serialized page data (no slug filter)."""
    if isinstance(data, dict):
        for key in ["url", "canonicalUrl"]:
            url_val = data.get(key, "")
            if url_val and f"/{media_type}/" in url_val and "umc." in url_val:
                if not url_val.startswith("http"):
                    url_val = f"https://tv.apple.com{url_val}"
                return url_val
        for v in data.values():
            result = _find_first_content_url(v, media_type)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_first_content_url(item, media_type)
            if result:
                return result
    return None


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
                    if score >= MINIMUM_TITLE_MATCH_SCORE:
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


def try_direct_slug_url(
    title: str, year: int = 0, is_movie: bool = True
) -> TrailerInfo | None:
    """Try to access Apple TV content directly using a title-based slug URL.
    
    Apple TV URLs follow the pattern:
    https://tv.apple.com/us/movie/{title-slug}/{content-id}
    
    This function tries multiple approaches:
    1. Direct page access using slug - try to access the page directly
    2. Search and filter by slug
    3. Look in serialized data for slug matches
    """
    logger.debug(f"Trying direct slug lookup for: {title}")
    
    slug = _title_to_slug(title)
    if not slug:
        return None
    
    media_type = "movie" if is_movie else "show"
    
    # Strategy 1: Try to directly fetch a page that might use the slug
    # Some Apple TV pages redirect or include the content even without the ID
    direct_url = f"https://tv.apple.com/us/{media_type}/{slug}"
    logger.debug(f"Trying direct slug URL: {direct_url}")
    
    try:
        response = requests.get(
            direct_url, headers=HEADERS, timeout=30, allow_redirects=True
        )
        if response.status_code != 200:
            response = requests.get(
                direct_url,
                headers=HEADERS,
                timeout=30,
                verify=False,
                allow_redirects=True,
            )
        
        if response.status_code == 200:
            # Check if we got redirected to a valid content page
            final_url = response.url
            if f"/{media_type}/" in final_url and "umc." in final_url:
                logger.debug(f"Redirected to: {final_url}")
                # Try to get trailer from this URL
                atvp = AppleTVPlus()
                trailers = atvp.get_trailers(final_url, default_only=True)
                if trailers:
                    trailer = trailers[0]
                    score = _calculate_match_score(
                        trailer.content_title, title, 0, year
                    )
                    if score >= MINIMUM_TITLE_MATCH_SCORE:
                        logger.info(
                            f"Found trailer via direct slug: {trailer.video_title}"
                        )
                        return trailer
            
            # Look for content ID in the page HTML
            soup = BeautifulSoup(response.text, "html.parser")
            script_tag = soup.find(
                "script",
                attrs={"type": "application/json", "id": "serialized-server-data"},
            )
            if script_tag:
                try:
                    data = json.loads(script_tag.text)
                    # Look for content with matching slug in URLs
                    found_url = _find_content_url_in_data(data, slug, media_type)
                    if found_url:
                        logger.debug(f"Found content URL in page data: {found_url}")
                        atvp = AppleTVPlus()
                        trailers = atvp.get_trailers(found_url, default_only=True)
                        if trailers:
                            trailer = trailers[0]
                            score = _calculate_match_score(
                                trailer.content_title, title, 0, year
                            )
                            if score >= MINIMUM_TITLE_MATCH_SCORE:
                                logger.info(
                                    f"Found trailer from page data: {trailer.video_title}"
                                )
                                return trailer
                except json.JSONDecodeError:
                    pass
    except Exception as e:
        logger.debug(f"Direct slug access failed: {e}")

    # Strategy 2: Search Apple TV and filter results by slug match
    search_term = f"{title} {year}" if year else title
    encoded_term = quote_plus(search_term)
    search_url = f"https://tv.apple.com/us/search?term={encoded_term}"
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=30)
        if response.status_code != 200:
            response = requests.get(
                search_url, headers=HEADERS, timeout=30, verify=False
            )
        if response.status_code != 200:
            return None
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Look for links that contain our slug
        links = soup.find_all("a", href=True)
        for link in links:
            href = link.get("href", "")
            # Check if the URL matches our expected pattern with the slug as a path segment
            if f"/us/{media_type}/" in href and _slug_in_url(slug, href):
                if not href.startswith("http"):
                    href = f"https://tv.apple.com{href}"
                
                logger.debug(f"Found matching slug URL: {href}")
                
                # Verify this URL has the content we want
                atvp = AppleTVPlus()
                trailers = atvp.get_trailers(href, default_only=True)
                if trailers:
                    trailer = trailers[0]
                    # Verify title match
                    score = _calculate_match_score(
                        trailer.content_title, title, 0, year
                    )
                    if score >= MINIMUM_TITLE_MATCH_SCORE:
                        logger.info(
                            f"Found matching trailer via slug URL: {trailer.video_title}"
                        )
                        return trailer
        
        # Also look in the serialized server data for matching content
        script_tag = soup.find(
            "script",
            attrs={"type": "application/json", "id": "serialized-server-data"},
        )
        if script_tag:
            try:
                data = json.loads(script_tag.text)
                # Recursively search for content matching our slug
                found_url = _find_url_by_slug_in_data(data, slug, media_type, title)
                if found_url:
                    atvp = AppleTVPlus()
                    trailers = atvp.get_trailers(found_url, default_only=True)
                    if trailers:
                        trailer = trailers[0]
                        score = _calculate_match_score(
                            trailer.content_title, title, 0, year
                        )
                        if score >= MINIMUM_TITLE_MATCH_SCORE:
                            return trailer
            except json.JSONDecodeError:
                pass
                
    except Exception as e:
        logger.debug(f"Direct slug lookup failed: {e}")
    
    return None


def _find_content_url_in_data(
    data: Any, slug: str, media_type: str
) -> str | None:
    """Find a content URL containing the slug in serialized page data."""
    if isinstance(data, dict):
        for key in ["url", "canonicalUrl", "href", "link"]:
            url_val = data.get(key, "")
            if url_val and isinstance(url_val, str):
                if f"/{media_type}/" in url_val and _slug_in_url(slug, url_val):
                    if "umc." in url_val:  # Has content ID
                        if not url_val.startswith("http"):
                            url_val = f"https://tv.apple.com{url_val}"
                        return url_val
        
        for v in data.values():
            result = _find_content_url_in_data(v, slug, media_type)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_content_url_in_data(item, slug, media_type)
            if result:
                return result
    return None


def _find_url_by_slug_in_data(
    data: Any, slug: str, media_type: str, title: str
) -> str | None:
    """Search recursively for a URL containing the slug in JSON data."""
    if isinstance(data, dict):
        # Check for URL fields
        for key in ["url", "canonicalUrl", "href"]:
            url_val = data.get(key, "")
            if url_val and isinstance(url_val, str):
                if f"/{media_type}/" in url_val and _slug_in_url(slug, url_val):
                    # Also verify title if present
                    item_title = data.get("title", "")
                    if item_title:
                        score = _calculate_match_score(item_title, title, 0, 0)
                        if score >= MINIMUM_TITLE_MATCH_SCORE:
                            if not url_val.startswith("http"):
                                url_val = f"https://tv.apple.com{url_val}"
                            return url_val
                    else:
                        if not url_val.startswith("http"):
                            url_val = f"https://tv.apple.com{url_val}"
                        return url_val
        
        # Recurse into values
        for v in data.values():
            result = _find_url_by_slug_in_data(v, slug, media_type, title)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_url_by_slug_in_data(item, slug, media_type, title)
            if result:
                return result
    return None


def search_for_trailer(
    media: MediaRead,
    exclude: list[str] | None = None,
) -> TrailerInfo | None:
    """Search for a trailer for the given media item.

    Uses multiple search strategies with validation at each step:
    1. IMDB ID lookup (most reliable when available)
    2. Direct slug-based URL lookup
    3. Apple TV API search with result validation  
    4. Apple TV web search with result validation
    5. iTunes API fallback with result validation
    
    Each strategy validates the trailer's content title matches the search title
    before returning, to avoid downloading wrong trailers.
    """
    logger.info(f"Searching Apple TV for trailer for '{media.title}'...")

    if not exclude:
        exclude = []

    # Strategy 0: Try IMDB ID lookup first (most reliable when available)
    if media.imdb_id:
        logger.debug(f"Trying IMDB lookup for: {media.imdb_id}")
        content_url = lookup_by_imdb_id(media.imdb_id, media.is_movie)
        if content_url:
            trailer = _fetch_and_validate_trailer(
                content_url, media.title, media.year, exclude
            )
            if trailer:
                return trailer

    # Strategy 1: Try direct slug-based lookup first (most reliable)
    # This generates a URL from the title and validates content matches
    trailer = try_direct_slug_url(media.title, media.year, media.is_movie)
    if trailer:
        if trailer.apple_id not in exclude:
            return trailer
        logger.debug(f"Trailer {trailer.apple_id} is in exclude list")

    # Strategy 2: Try Apple TV internal search API
    # Loop through results until we find one that validates
    api_results = search_apple_tv_api(media.title, media.year, media.is_movie)
    for result in api_results:
        content_url = result.get("url")
        if not content_url and result.get("id"):
            media_type = "movie" if media.is_movie else "show"
            content_url = f"https://tv.apple.com/us/{media_type}/-/{result['id']}"
        
        if content_url:
            trailer = _fetch_and_validate_trailer(
                content_url, media.title, media.year, exclude
            )
            if trailer:
                return trailer

    # Strategy 3: Try Apple TV web search
    content_url = search_apple_tv_web(media.title, media.year, media.is_movie)
    if content_url:
        trailer = _fetch_and_validate_trailer(
            content_url, media.title, media.year, exclude
        )
        if trailer:
            return trailer

    # Strategy 4: Try iTunes API fallback
    itunes_results = search_apple_itunes(media.title, media.year, media.is_movie)
    for result in itunes_results:
        track_id = result.get("trackId") or result.get("collectionId")
        track_url = result.get("trackViewUrl", "")

        # Try to extract Apple TV URL from iTunes URL
        content_url = None
        if track_url:
            try:
                parsed = urlparse(track_url)
                if parsed.netloc.endswith(".apple.com") or parsed.netloc == "apple.com":
                    if "/movie/" in track_url or "/tv-season/" in track_url:
                        content_url = track_url.replace(
                            "itunes.apple.com", "tv.apple.com"
                        )
            except Exception:
                pass

        if not content_url and track_id:
            media_type = "movie" if media.is_movie else "show"
            content_url = f"https://tv.apple.com/us/{media_type}/-/{track_id}"

        if content_url:
            trailer = _fetch_and_validate_trailer(
                content_url, media.title, media.year, exclude
            )
            if trailer:
                return trailer

    logger.warning(f"No Apple TV content found for '{media.title}' [{media.id}]")
    return None


def _fetch_and_validate_trailer(
    content_url: str,
    search_title: str,
    search_year: int,
    exclude: list[str],
) -> TrailerInfo | None:
    """Fetch trailer from URL and validate it matches the search title.
    
    Returns the trailer only if it passes validation, otherwise None.
    """
    logger.debug(f"Attempting to fetch trailer from: {content_url}")

    try:
        atvp = AppleTVPlus()
        trailers = atvp.get_trailers(content_url, default_only=True)

        if not trailers:
            logger.debug(f"No trailers returned from URL: {content_url}")
            return None

        for trailer in trailers:
            # Validate that the content title matches our search
            content_score = _calculate_match_score(
                trailer.content_title,
                search_title,
                0,  # Don't use year for title check
                0,
            )
            
            if content_score < MINIMUM_TITLE_MATCH_SCORE:
                logger.debug(
                    f"Trailer '{trailer.content_title}' doesn't match "
                    f"'{search_title}' (score: {content_score})"
                )
                continue

            # Check exclusion list
            if trailer.apple_id and trailer.apple_id in exclude:
                logger.debug(f"Trailer {trailer.apple_id} is in exclude list")
                continue

            logger.info(
                f"Found trailer for '{search_title}': {trailer.video_title}"
            )
            return trailer

    except Exception as e:
        logger.debug(f"Failed to get trailer from {content_url}: {e}")

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
