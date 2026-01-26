"""HLS stream parser for Apple TV trailers."""

from dataclasses import dataclass
from urllib.parse import urlparse

import m3u8

from app_logger import ModuleLogger

logger = ModuleLogger("AppleHLS")


@dataclass
class VideoStreamInfo:
    """Information about a video stream."""

    stream_type: str = "video"
    video_range: str = "SDR"
    fps: float = 0.0
    codec: str = "HEVC"
    resolution: tuple[int, int] = (0, 0)
    bitrate: str = "0 Mb/s"
    uri: str = ""

    @property
    def width(self) -> int:
        return self.resolution[0]

    @property
    def height(self) -> int:
        return self.resolution[1]


@dataclass
class AudioStreamInfo:
    """Information about an audio stream."""

    stream_type: str = "audio"
    name: str = ""
    language: str = "en"
    is_ad: bool = False
    is_original: bool = False
    channels: str = "2"
    codec: str = "AAC"
    bitrate: str = "0 Kb/s"
    uri: str = ""


@dataclass
class SubtitleStreamInfo:
    """Information about a subtitle stream."""

    stream_type: str = "subtitle"
    name: str = ""
    language: str = "en"
    is_forced: bool = False
    is_sdh: bool = False
    uri: str = ""


@dataclass
class HLSStreamInfo:
    """Container for all HLS stream information."""

    video: list[VideoStreamInfo]
    audio: list[AudioStreamInfo]
    subtitle: list[SubtitleStreamInfo]


def get_hls_streams(url: str) -> HLSStreamInfo | None:
    """Parse HLS playlist and extract stream information."""
    try:
        logger.debug("Loading HLS url...")
        data = m3u8.load(url)
    except Exception:
        logger.warning("SSL failed, trying without SSL verification...")
        try:
            data = m3u8.load(url, verify_ssl=False)
        except Exception as e:
            logger.error(f"Failed to load HLS playlist: {e}")
            return None

    video_streams: list[VideoStreamInfo] = []
    audio_streams: list[AudioStreamInfo] = []
    subtitle_streams: list[SubtitleStreamInfo] = []

    # Parse video playlists
    for v in data.playlists:
        if video_streams:
            previous_uri = video_streams[-1].uri
            previous_uri_path = urlparse(previous_uri).path
            current_uri_path = urlparse(v.uri).path

            if previous_uri_path == current_uri_path:
                continue

        codec = v.stream_info.codecs or ""
        video_range = v.stream_info.video_range or "SDR"

        if "PQ" in video_range:
            video_range = "HDR"
        if "avc" in codec.lower():
            codec = "AVC"
        elif "hvc" in codec.lower():
            codec = "HEVC"
        if "dvh" in codec.lower():
            codec = "HEVC"
            video_range = "DoVi"

        resolution = v.stream_info.resolution or (0, 0)
        avg_bandwidth = v.stream_info.average_bandwidth or 0
        bitrate = f"{round(avg_bandwidth / 1000000, 2)} Mb/s"

        video_streams.append(
            VideoStreamInfo(
                video_range=video_range,
                fps=v.stream_info.frame_rate or 0.0,
                codec=codec,
                resolution=resolution,
                bitrate=bitrate,
                uri=v.uri,
            )
        )

    # Parse audio and subtitle media
    for m in data.media:
        if m.type == "AUDIO":
            if audio_streams:
                previous_uri = audio_streams[-1].uri
                previous_uri_path = urlparse(previous_uri).path
                current_uri_path = urlparse(m.uri).path if m.uri else ""

                if previous_uri_path == current_uri_path:
                    continue

            is_ad = False
            is_original = False

            characteristics = m.characteristics or ""
            if "original-content" in characteristics:
                is_original = True
            if "accessibility" in characteristics:
                is_ad = True

            group_id = m.group_id or ""
            codec = "AAC"

            if "atmos" in group_id.lower():
                codec = "Atmos"
            elif "ac3" in group_id.lower():
                codec = "DD5.1"
            elif "stereo" in group_id.lower():
                if "HE" in group_id:
                    codec = "HE-AAC"
                else:
                    codec = "AAC"

            bitrate = "0 Kb/s"
            uri = m.uri or ""
            if "gr32" in uri:
                bitrate = "32 Kb/s"
            elif "gr64" in uri:
                bitrate = "64 Kb/s"
            elif "gr160" in uri:
                bitrate = "160 Kb/s"
            elif "gr384" in uri:
                bitrate = "384 Kb/s"
            elif "gr2448" in uri:
                bitrate = "488 Kb/s"

            audio_streams.append(
                AudioStreamInfo(
                    name=m.name or "",
                    language=m.language or "und",
                    is_ad=is_ad,
                    is_original=is_original,
                    channels=m.channels or "2",
                    codec=codec,
                    bitrate=bitrate,
                    uri=uri,
                )
            )

        elif m.type == "SUBTITLES":
            if subtitle_streams:
                previous_uri = subtitle_streams[-1].uri
                previous_uri_path = urlparse(previous_uri).path
                current_uri_path = urlparse(m.uri).path if m.uri else ""

                if previous_uri_path == current_uri_path:
                    continue

            is_sdh = False
            characteristics = m.characteristics or ""
            if "accessibility" in characteristics:
                is_sdh = True

            subtitle_streams.append(
                SubtitleStreamInfo(
                    name=m.name or "",
                    language=m.language or "und",
                    is_forced=m.forced == "YES",
                    is_sdh=is_sdh,
                    uri=m.uri or "",
                )
            )

    return HLSStreamInfo(
        video=video_streams,
        audio=audio_streams,
        subtitle=subtitle_streams,
    )


def select_best_streams(
    hls_info: HLSStreamInfo,
    max_resolution: int = 0,
    preferred_language: str = "en",
) -> tuple[VideoStreamInfo | None, AudioStreamInfo | None]:
    """Select the best video and audio streams based on preferences."""
    # Select best video (highest resolution up to max_resolution)
    video_streams = hls_info.video.copy()
    if not video_streams:
        return None, None

    # Sort by resolution (width * height) descending
    video_streams.sort(
        key=lambda x: x.resolution[0] * x.resolution[1], reverse=True
    )

    selected_video = None
    for stream in video_streams:
        if max_resolution == 0 or stream.height <= max_resolution:
            selected_video = stream
            break

    if not selected_video and video_streams:
        selected_video = video_streams[-1]  # Take lowest if all exceed max

    # Select best audio (prefer non-AD, highest bitrate, matching language)
    audio_streams = hls_info.audio.copy()
    if not audio_streams:
        return selected_video, None

    # Filter non-AD streams
    non_ad_audio = [a for a in audio_streams if not a.is_ad]
    if non_ad_audio:
        audio_streams = non_ad_audio

    # Prefer matching language
    matching_lang = [
        a
        for a in audio_streams
        if a.language.startswith(preferred_language)
    ]
    if matching_lang:
        audio_streams = matching_lang

    # Sort by bitrate descending (parse bitrate string)
    def parse_bitrate(bitrate_str: str) -> int:
        try:
            value = float(bitrate_str.split()[0])
            if "Mb" in bitrate_str:
                value *= 1000
            return int(value)
        except Exception:
            return 0

    audio_streams.sort(key=lambda x: parse_bitrate(x.bitrate), reverse=True)

    selected_audio = audio_streams[0] if audio_streams else None

    return selected_video, selected_audio
