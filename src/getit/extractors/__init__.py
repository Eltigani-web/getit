from getit.extractors.base import BaseExtractor, ExtractorError, FileInfo

# Import extractor modules to trigger @ExtractorRegistry.register decorators
from . import gofile, mega, mediafire, onefichier, pixeldrain

__all__ = ["BaseExtractor", "FileInfo", "ExtractorError"]
