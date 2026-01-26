"""Tests for Apple HLS module."""

import pytest
from core.download.apple.hls import (
    VideoStreamInfo,
    AudioStreamInfo,
    SubtitleStreamInfo,
    HLSStreamInfo,
    select_best_streams,
)


class TestVideoStreamInfo:
    """Tests for VideoStreamInfo dataclass."""

    def test_video_stream_defaults(self):
        """Test VideoStreamInfo with default values."""
        stream = VideoStreamInfo()
        assert stream.stream_type == "video"
        assert stream.video_range == "SDR"
        assert stream.fps == 0.0
        assert stream.codec == "HEVC"
        assert stream.resolution == (0, 0)
        assert stream.width == 0
        assert stream.height == 0
        assert stream.bitrate == "0 Mb/s"
        assert stream.uri == ""

    def test_video_stream_with_values(self):
        """Test VideoStreamInfo with custom values."""
        stream = VideoStreamInfo(
            video_range="HDR",
            fps=24.0,
            codec="AVC",
            resolution=(1920, 1080),
            bitrate="5.5 Mb/s",
            uri="https://example.com/video.m3u8",
        )
        assert stream.video_range == "HDR"
        assert stream.fps == 24.0
        assert stream.codec == "AVC"
        assert stream.resolution == (1920, 1080)
        assert stream.width == 1920
        assert stream.height == 1080
        assert stream.bitrate == "5.5 Mb/s"


class TestAudioStreamInfo:
    """Tests for AudioStreamInfo dataclass."""

    def test_audio_stream_defaults(self):
        """Test AudioStreamInfo with default values."""
        stream = AudioStreamInfo()
        assert stream.stream_type == "audio"
        assert stream.name == ""
        assert stream.language == "en"
        assert stream.is_ad is False
        assert stream.is_original is False
        assert stream.channels == "2"
        assert stream.codec == "AAC"

    def test_audio_stream_with_values(self):
        """Test AudioStreamInfo with custom values."""
        stream = AudioStreamInfo(
            name="English",
            language="en",
            is_ad=False,
            is_original=True,
            channels="6",
            codec="Atmos",
            bitrate="384 Kb/s",
            uri="https://example.com/audio.m3u8",
        )
        assert stream.name == "English"
        assert stream.is_original is True
        assert stream.channels == "6"
        assert stream.codec == "Atmos"


class TestSubtitleStreamInfo:
    """Tests for SubtitleStreamInfo dataclass."""

    def test_subtitle_stream_defaults(self):
        """Test SubtitleStreamInfo with default values."""
        stream = SubtitleStreamInfo()
        assert stream.stream_type == "subtitle"
        assert stream.name == ""
        assert stream.language == "en"
        assert stream.is_forced is False
        assert stream.is_sdh is False


class TestSelectBestStreams:
    """Tests for select_best_streams function."""

    def test_select_best_streams_empty(self):
        """Test selecting from empty HLS info."""
        hls_info = HLSStreamInfo(video=[], audio=[], subtitle=[])
        video, audio = select_best_streams(hls_info)
        assert video is None
        assert audio is None

    def test_select_best_video_highest_resolution(self):
        """Test selecting highest resolution video."""
        video_streams = [
            VideoStreamInfo(resolution=(1280, 720), uri="720p"),
            VideoStreamInfo(resolution=(1920, 1080), uri="1080p"),
            VideoStreamInfo(resolution=(3840, 2160), uri="2160p"),
        ]
        hls_info = HLSStreamInfo(video=video_streams, audio=[], subtitle=[])

        video, audio = select_best_streams(hls_info, max_resolution=0)
        assert video.uri == "2160p"

    def test_select_best_video_with_max_resolution(self):
        """Test selecting video within max resolution limit."""
        video_streams = [
            VideoStreamInfo(resolution=(1280, 720), uri="720p"),
            VideoStreamInfo(resolution=(1920, 1080), uri="1080p"),
            VideoStreamInfo(resolution=(3840, 2160), uri="2160p"),
        ]
        hls_info = HLSStreamInfo(video=video_streams, audio=[], subtitle=[])

        video, audio = select_best_streams(hls_info, max_resolution=1080)
        assert video.uri == "1080p"

    def test_select_best_audio_non_ad(self):
        """Test selecting non-AD audio stream."""
        audio_streams = [
            AudioStreamInfo(
                name="English AD", language="en", is_ad=True, bitrate="384 Kb/s"
            ),
            AudioStreamInfo(
                name="English", language="en", is_ad=False, bitrate="384 Kb/s"
            ),
        ]
        video_streams = [VideoStreamInfo(resolution=(1920, 1080))]
        hls_info = HLSStreamInfo(
            video=video_streams, audio=audio_streams, subtitle=[]
        )

        video, audio = select_best_streams(hls_info)
        assert audio.name == "English"
        assert audio.is_ad is False

    def test_select_best_audio_preferred_language(self):
        """Test selecting audio with preferred language."""
        audio_streams = [
            AudioStreamInfo(name="French", language="fr", bitrate="384 Kb/s"),
            AudioStreamInfo(name="English", language="en", bitrate="384 Kb/s"),
            AudioStreamInfo(name="Spanish", language="es", bitrate="384 Kb/s"),
        ]
        video_streams = [VideoStreamInfo(resolution=(1920, 1080))]
        hls_info = HLSStreamInfo(
            video=video_streams, audio=audio_streams, subtitle=[]
        )

        video, audio = select_best_streams(hls_info, preferred_language="en")
        assert audio.language == "en"
