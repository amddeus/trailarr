"""Apple TV trailer downloader using HLS streams."""

import asyncio
import os
import subprocess
import tempfile
import time

import aiohttp
import m3u8

from app_logger import ModuleLogger
from config.settings import app_settings
from core.base.database.models.trailerprofile import TrailerProfileRead
from core.download.apple.api import TrailerInfo
from core.download.apple.hls import (
    get_hls_streams,
    select_best_streams,
)
from exceptions import DownloadFailedError

logger = ModuleLogger("AppleDownloader")


async def _fetch_segment(
    session: aiohttp.ClientSession,
    url: str,
    output_path: str,
    ssl: bool = True,
) -> bool:
    """Fetch a single HLS segment."""
    try:
        async with session.get(url, ssl=ssl) as response:
            if response.status != 200:
                return False
            content = await response.read()
            with open(output_path, "wb") as f:
                f.write(content)
            return True
    except Exception as e:
        logger.debug(f"Segment download failed: {e}")
        return False


async def _download_hls_stream(
    stream_url: str,
    output_file: str,
    stream_type: str = "video",
    ssl: bool = True,
) -> bool:
    """Download all segments from an HLS stream and concatenate them."""
    logger.debug(f"Downloading {stream_type} stream...")

    try:
        # Load the stream playlist
        try:
            playlist = m3u8.load(stream_url, verify_ssl=ssl)
        except Exception:
            if ssl:
                playlist = m3u8.load(stream_url, verify_ssl=False)
                ssl = False
            else:
                raise

        base_uri = os.path.dirname(stream_url)
        segments: list[str] = []

        # Get init segment if exists
        if playlist.segment_map:
            init_uri = playlist.segment_map[0].uri
            if not init_uri.startswith("http"):
                init_uri = f"{base_uri}/{init_uri}"
            segments.append(init_uri)

        # Get all segment URIs
        for seg in playlist.segments:
            seg_uri = seg.uri
            if not seg_uri.startswith("http"):
                seg_uri = f"{base_uri}/{seg_uri}"
            if seg_uri not in segments:
                segments.append(seg_uri)

        if not segments:
            logger.error(f"No segments found in {stream_type} stream")
            return False

        logger.debug(f"Downloading {len(segments)} {stream_type} segments...")

        # Download segments concurrently
        with tempfile.TemporaryDirectory() as temp_dir:
            segment_files: list[str] = []

            connector = aiohttp.TCPConnector(limit=10, ssl=ssl)
            timeout = aiohttp.ClientTimeout(total=300)

            async with aiohttp.ClientSession(
                connector=connector, timeout=timeout
            ) as session:
                tasks = []
                for i, seg_url in enumerate(segments):
                    seg_file = os.path.join(temp_dir, f"seg_{i:05d}.ts")
                    segment_files.append(seg_file)
                    tasks.append(
                        _fetch_segment(session, seg_url, seg_file, ssl)
                    )

                results = await asyncio.gather(*tasks)

                if not all(results):
                    # Retry failed segments without SSL
                    if ssl:
                        for i, (result, seg_url) in enumerate(
                            zip(results, segments)
                        ):
                            if not result:
                                seg_file = segment_files[i]
                                success = await _fetch_segment(
                                    session, seg_url, seg_file, False
                                )
                                if not success:
                                    logger.error(
                                        f"Failed to download segment: {seg_url}"
                                    )
                                    return False
                    else:
                        logger.error("Some segments failed to download")
                        return False

            # Concatenate all segments
            with open(output_file, "wb") as outfile:
                for seg_file in segment_files:
                    if os.path.exists(seg_file):
                        with open(seg_file, "rb") as infile:
                            outfile.write(infile.read())

        logger.debug(f"{stream_type.capitalize()} stream downloaded")
        return True

    except Exception as e:
        logger.error(f"HLS stream download failed: {e}")
        return False


def _mux_streams(
    video_file: str | None,
    audio_file: str | None,
    output_file: str,
    profile: TrailerProfileRead,
) -> bool:
    """Mux video and audio streams using FFmpeg."""
    logger.debug("Muxing streams with FFmpeg...")

    ffmpeg_path = app_settings.ffmpeg_path

    cmd: list[str] = [ffmpeg_path, "-y"]

    if video_file and os.path.exists(video_file):
        cmd.extend(["-i", video_file])
    if audio_file and os.path.exists(audio_file):
        cmd.extend(["-i", audio_file])

    # Map streams
    stream_idx = 0
    if video_file and os.path.exists(video_file):
        cmd.extend(["-map", f"{stream_idx}:v"])
        stream_idx += 1
    if audio_file and os.path.exists(audio_file):
        cmd.extend(["-map", f"{stream_idx}:a"])

    # Video codec settings
    if profile.video_format == "copy":
        cmd.extend(["-c:v", "copy"])
    else:
        # Use appropriate encoder based on profile
        video_codecs = {
            "h264": "libx264",
            "h265": "libx265",
            "vp8": "libvpx",
            "vp9": "libvpx-vp9",
            "av1": "libaom-av1",
        }
        codec = video_codecs.get(profile.video_format, "libx264")
        cmd.extend(["-c:v", codec])

        # Add quality settings
        if profile.video_format in ["h264", "h265"]:
            cmd.extend(["-preset", "fast", "-crf", "22"])

    # Audio codec settings
    if profile.audio_format == "copy":
        cmd.extend(["-c:a", "copy"])
    else:
        audio_codecs = {
            "aac": "aac",
            "ac3": "ac3",
            "eac3": "eac3",
            "mp3": "libmp3lame",
            "flac": "flac",
            "opus": "libopus",
        }
        codec = audio_codecs.get(profile.audio_format, "aac")
        cmd.extend(["-c:a", codec, "-b:a", "128k"])

    cmd.append(output_file)

    logger.debug(f"FFmpeg command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=app_settings.ffmpeg_timeout * 60,
            encoding="utf-8",
            errors="replace",
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg muxing failed: {result.stderr}")
            return False

        logger.debug("Streams muxed successfully")
        return True

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg muxing timed out")
        return False
    except Exception as e:
        logger.error(f"FFmpeg muxing error: {e}")
        return False


async def download_apple_trailer(
    trailer_info: TrailerInfo,
    output_file: str,
    profile: TrailerProfileRead,
) -> str:
    """Download a trailer from Apple TV using HLS streams."""
    logger.info(
        f"Downloading Apple trailer: {trailer_info.video_title} "
        f"for {trailer_info.content_title}"
    )

    start_time = time.perf_counter()

    # Get HLS stream information
    hls_info = get_hls_streams(trailer_info.hls_url)
    if not hls_info:
        raise DownloadFailedError("Failed to parse HLS playlist")

    # Select best streams based on profile settings
    preferred_lang = (
        profile.subtitles_language[:2]
        if len(profile.subtitles_language) >= 2
        else profile.subtitles_language
    )
    video_stream, audio_stream = select_best_streams(
        hls_info,
        max_resolution=profile.video_resolution,
        preferred_language=preferred_lang,
    )

    if not video_stream and not audio_stream:
        raise DownloadFailedError("No suitable streams found")

    # Create temp directory for intermediate files
    temp_dir = "/var/lib/trailarr/tmp"
    if not os.path.exists(temp_dir):
        temp_dir = "/app/tmp"
    if not os.path.exists(temp_dir):
        temp_dir = tempfile.gettempdir()

    os.makedirs(temp_dir, exist_ok=True)

    video_temp = os.path.join(temp_dir, "video_temp.ts")
    audio_temp = os.path.join(temp_dir, "audio_temp.ts")

    try:
        # Download video stream
        if video_stream:
            logger.debug(
                f"Downloading video: {video_stream.resolution} "
                f"{video_stream.codec} {video_stream.video_range}"
            )
            success = await _download_hls_stream(
                video_stream.uri, video_temp, "video"
            )
            if not success:
                raise DownloadFailedError("Failed to download video stream")

        # Download audio stream
        if audio_stream:
            logger.debug(
                f"Downloading audio: {audio_stream.codec} "
                f"{audio_stream.language}"
            )
            success = await _download_hls_stream(
                audio_stream.uri, audio_temp, "audio"
            )
            if not success:
                raise DownloadFailedError("Failed to download audio stream")

        # Mux streams
        video_path = video_temp if os.path.exists(video_temp) else None
        audio_path = audio_temp if os.path.exists(audio_temp) else None

        if not _mux_streams(video_path, audio_path, output_file, profile):
            raise DownloadFailedError("Failed to mux streams")

        # Verify output file exists
        if not os.path.exists(output_file):
            raise DownloadFailedError("Output file not created")

        elapsed = time.perf_counter() - start_time
        logger.info(f"Apple trailer downloaded in {elapsed:.2f}s")

        return output_file

    finally:
        # Cleanup temp files
        for temp_file in [video_temp, audio_temp]:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass


def download_apple_trailer_sync(
    trailer_info: TrailerInfo,
    output_file: str,
    profile: TrailerProfileRead,
) -> str:
    """Synchronous wrapper for download_apple_trailer."""
    return asyncio.run(
        download_apple_trailer(trailer_info, output_file, profile)
    )
