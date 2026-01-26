"""Apple TV trailer download modules."""

from core.download.apple.api import AppleTVPlus
from core.download.apple.hls import get_hls_streams, HLSStreamInfo
from core.download.apple.downloader import download_apple_trailer

__all__ = [
    "AppleTVPlus",
    "get_hls_streams",
    "HLSStreamInfo",
    "download_apple_trailer",
]
