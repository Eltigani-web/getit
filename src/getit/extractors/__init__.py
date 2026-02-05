from getit.extractors.base import BaseExtractor, ExtractorError, FileInfo

# Import extractor modules to trigger @ExtractorRegistry.register decorators
from . import gofile, mediafire, mega, onefichier, pixeldrain

__all__ = [
    "BaseExtractor",
    "ExtractorError",
    "FileInfo",
    "gofile",
    "mega",
    "mediafire",
    "onefichier",
    "pixeldrain",
]
