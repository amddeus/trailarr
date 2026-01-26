"""Apple TV Plus API client for fetching trailer information."""

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from app_logger import ModuleLogger

logger = ModuleLogger("AppleTVAPI")

HEADERS = {
    "content-type": "application/json",
    "accept-encoding": "gzip, deflate, br",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://tv.apple.com",
    "referer": "https://tv.apple.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    ),
}


class TrailerInfo:
    """Trailer information from Apple TV."""

    def __init__(
        self,
        hls_url: str,
        video_title: str,
        content_title: str,
        release_date: str,
        description: str = "",
        genres: list[str] | None = None,
        cover_url: str | None = None,
        apple_id: str | None = None,
    ):
        self.hls_url = hls_url
        self.video_title = video_title
        self.content_title = content_title
        self.release_date = release_date
        self.description = description
        self.genres = genres or []
        self.cover_url = cover_url
        self.apple_id = apple_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "hls_url": self.hls_url,
            "video_title": self.video_title,
            "content_title": self.content_title,
            "release_date": self.release_date,
            "description": self.description,
            "genres": self.genres,
            "cover_url": self.cover_url,
            "apple_id": self.apple_id,
        }


class AppleTVPlus:
    """Client for interacting with Apple TV Plus API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers = HEADERS.copy()
        self.locale = "en-US"
        self.storefront = "143441"  # US storefront
        self.locale_code = "us"
        self.kind = "movie"
        self.id = ""
        self.target_id: str | None = None
        self.target_type: str | None = None
        self._get_access_token()

    def _get_access_token(self):
        """Fetch access token from Apple TV website."""
        logger.debug("Fetching access-token from Apple TV...")

        try:
            r = requests.get(
                "https://tv.apple.com/us", headers=HEADERS, timeout=30
            )
        except requests.exceptions.RequestException:
            logger.warning("SSL failed, trying without SSL verification...")
            try:
                r = requests.get(
                    "https://tv.apple.com/us",
                    headers=HEADERS,
                    verify=False,
                    timeout=30,
                )
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to fetch page: {e}")
                self._use_fallback_token()
                return

        if r.status_code != 200:
            logger.warning(
                f"Failed to get https://tv.apple.com/. Status: {r.status_code}"
            )
            self._use_fallback_token()
            return

        soup = BeautifulSoup(r.text, "html.parser")

        # Try to find the serialized server data
        script_tag = soup.find(
            "script",
            attrs={"type": "application/json", "id": "serialized-server-data"},
        )

        if script_tag:
            try:
                data = json.loads(script_tag.text)
                if isinstance(data, list) and len(data) > 0:
                    access_token = self._find_token_recursive(data)
                    if access_token:
                        self.session.headers.update(
                            {"authorization": f"Bearer {access_token}"}
                        )
                        logger.debug("Successfully obtained access token")
                        return
            except json.JSONDecodeError:
                pass

        # Try to find token in script tags
        scripts = soup.find_all("script")
        for script in scripts:
            if script.string:
                match = re.search(
                    r'"developerToken"\s*:\s*"([^"]+)"', script.string
                )
                if match:
                    access_token = match.group(1)
                    self.session.headers.update(
                        {"authorization": f"Bearer {access_token}"}
                    )
                    logger.debug("Successfully obtained access token from script")
                    return

        logger.warning(
            "Could not extract access token, using fallback method"
        )
        self._use_fallback_token()

    def _find_token_recursive(
        self, obj: Any, key: str = "developerToken"
    ) -> str | None:
        """Recursively search for a key in a nested dict/list structure."""
        if isinstance(obj, dict):
            if key in obj:
                return obj[key]
            for v in obj.values():
                result = self._find_token_recursive(v, key)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = self._find_token_recursive(item, key)
                if result:
                    return result
        return None

    def _use_fallback_token(self):
        """Use fallback method to access API without token."""
        logger.debug("Using fallback API access method")
        self.session.headers.pop("authorization", None)

    def _parse_url(self, url: str) -> bool:
        """Parse and validate the Apple TV+ URL."""
        logger.debug(f"Parsing Apple TV URL: {url}")

        u = urlparse(url)

        if not u.scheme:
            url = f"https://{url}"
            u = urlparse(url)

        if u.netloc != "tv.apple.com":
            logger.error("URL is invalid! Host should be tv.apple.com!")
            return False

        path_parts = [p for p in u.path.split("/") if p]

        if len(path_parts) < 3:
            logger.error("URL format not recognized!")
            return False

        self.locale_code = path_parts[0]
        self.kind = path_parts[1]

        if len(path_parts) >= 4:
            self.id = path_parts[-1]
        else:
            self.id = path_parts[-1]

        query_params = parse_qs(u.query)
        if "targetId" in query_params:
            self.target_id = query_params["targetId"][0]
            self.target_type = query_params.get("targetType", ["Movie"])[0]
        else:
            self.target_id = None
            self.target_type = None

        if self.kind in ["episode", "season"]:
            self.kind = "show"
            if "showId" in query_params:
                self.id = query_params["showId"][0]
        elif self.kind == "clip":
            if self.target_id:
                self.id = self.target_id
                self.kind = (
                    self.target_type.lower() if self.target_type else "movie"
                )

        logger.debug(f"Parsed: kind={self.kind}, id={self.id}")
        return True

    def _get_api_data(self) -> dict[str, Any] | None:
        """Fetch content data from Apple TV+ API."""
        logger.debug("Fetching API response...")

        api_url = f"https://tv.apple.com/api/uts/v3/{self.kind}s/{self.id}"
        params = {
            "caller": "web",
            "locale": self.locale,
            "pfm": "appletv",
            "sf": self.storefront,
            "utscf": "OjAAAAAAAAA~",
            "utsk": "6e3013c6d6fae3c2::::::235656c069bb0efb",
            "v": "72",
        }

        try:
            r = self.session.get(url=api_url, params=params, timeout=30)
        except requests.exceptions.RequestException:
            logger.warning("SSL failed, trying without SSL verification...")
            try:
                r = self.session.get(
                    url=api_url, params=params, verify=False, timeout=30
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch API: {e}")
                return None

        if r.status_code != 200:
            logger.error(f"API returned status {r.status_code}")
            return None

        try:
            return r.json()
        except json.JSONDecodeError:
            logger.error("Failed to parse API response as JSON")
            return None

    def _parse_genres(self, genre: Any) -> list[str]:
        """Parse genres from API response."""
        if not isinstance(genre, list):
            genre = [genre]
        return [
            g.get("name", g) if isinstance(g, dict) else str(g) for g in genre
        ]

    def _parse_date(self, date: Any) -> str:
        """Parse date from API response."""
        if isinstance(date, (int, float)):
            return datetime.utcfromtimestamp(date / 1000.0).strftime("%Y-%m-%d")
        elif isinstance(date, str):
            return date[:10]
        return datetime.now().strftime("%Y-%m-%d")

    def _get_default_trailer(self) -> TrailerInfo | None:
        """Get the default/main trailer for the content."""
        data = self._get_api_data()

        if not data:
            logger.error("Failed to get API data")
            return None

        try:
            content = data.get("data", {}).get("content", {})

            bg_video = content.get("backgroundVideo")
            if not bg_video:
                playables = content.get("playables", [])
                bg_video = playables[0] if playables else None

            if not bg_video:
                logger.error("No background video found in API response")
                return None

            cover_image = None
            try:
                images = bg_video.get("images", {}).get("contentImage", {})
                if images.get("url"):
                    cover_image = images["url"].format(
                        w=images.get("width", 1920),
                        h=images.get("height", 1080),
                        f="jpg",
                    )
            except Exception:
                pass

            assets = bg_video.get("assets", {})
            hls_url = (
                assets.get("hlsUrl") or assets.get("hls") or assets.get("url")
            )

            if not hls_url:
                logger.error("No HLS URL found in API response")
                return None

            return TrailerInfo(
                hls_url=hls_url,
                video_title=bg_video.get("title", "Trailer"),
                content_title=content.get("title", "Unknown"),
                release_date=self._parse_date(content.get("releaseDate")),
                description=content.get("description", ""),
                genres=self._parse_genres(content.get("genres", [])),
                cover_url=cover_image,
                apple_id=self.id,
            )
        except Exception as e:
            logger.error(f"Error parsing API response: {e}")
            return None

    def _get_all_trailers(self) -> list[TrailerInfo]:
        """Get all available trailers for the content."""
        data = self._get_api_data()

        if not data:
            logger.error("Failed to get API data")
            return []

        trailers: list[TrailerInfo] = []

        try:
            content = data.get("data", {}).get("content", {})
            canvas = data.get("data", {}).get("canvas", {})

            shelves = canvas.get("shelves", [])
            background_videos = None

            for shelf in shelves:
                shelf_title = shelf.get("title", "").lower()
                if any(
                    keyword in shelf_title
                    for keyword in ["trailer", "clip", "video"]
                ):
                    background_videos = shelf.get("items", [])
                    break

            if not background_videos:
                playables = content.get("playables", [])
                if playables:
                    background_videos = [{"playables": playables}]

            if background_videos:
                for item in background_videos:
                    try:
                        if "playables" in item:
                            playable = (
                                item["playables"][0]
                                if item["playables"]
                                else None
                            )
                        else:
                            playable = item

                        if not playable:
                            continue

                        assets = playable.get("assets", {})
                        hls_url = (
                            assets.get("hlsUrl")
                            or assets.get("hls")
                            or assets.get("url")
                        )

                        if not hls_url:
                            continue

                        cover_image = None
                        try:
                            canonical = playable.get(
                                "canonicalMetadata", playable
                            )
                            images = canonical.get("images", {}).get(
                                "contentImage", {}
                            )
                            if images.get("url"):
                                cover_image = images["url"].format(
                                    w=images.get("width", 1920),
                                    h=images.get("height", 1080),
                                    f="jpg",
                                )
                        except Exception:
                            pass

                        trailers.append(
                            TrailerInfo(
                                hls_url=hls_url,
                                video_title=playable.get("title", "Trailer"),
                                content_title=content.get("title", "Unknown"),
                                release_date=self._parse_date(
                                    content.get("releaseDate")
                                ),
                                description=content.get("description", ""),
                                genres=self._parse_genres(
                                    content.get("genres", [])
                                ),
                                cover_url=cover_image,
                                apple_id=self.id,
                            )
                        )
                    except Exception as e:
                        logger.debug(f"Error processing trailer item: {e}")
                        continue

            if not trailers:
                default = self._get_default_trailer()
                if default:
                    return [default]

            return trailers

        except Exception as e:
            logger.error(f"Error getting trailers: {e}")
            default = self._get_default_trailer()
            return [default] if default else []

    def get_trailers(
        self, url: str, default_only: bool = False
    ) -> list[TrailerInfo]:
        """Get trailer information for the given URL."""
        if not self._parse_url(url):
            return []

        if default_only:
            result = self._get_default_trailer()
            return [result] if result else []
        else:
            return self._get_all_trailers()
