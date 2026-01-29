"""
getit - Universal file hosting downloader with TUI

Supports: GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz
"""

from importlib.metadata import PackageNotFoundError, version


def __set_git_version__() -> str:
    """
    Determine the package version from git tags using setuptools_scm.
    
    Returns:
        str: Version string derived from git tags, or "0.1.0" if package metadata is unavailable.
    """
    try:
        return version("getit-cli")
    except PackageNotFoundError:
        # Package not installed, fallback to default
        return "0.1.0"


__version__ = __set_git_version__()
__author__ = "getit contributors"

from getit.config import Settings

__all__ = ["__version__", "Settings"]