"""
getit - Universal file hosting downloader with TUI

Supports: GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz
"""

from importlib.metadata import PackageNotFoundError, version

from getit.config import Settings


def __set_git_version__() -> str:
    """Get version from git tags via setuptools_scm (single source of truth).

    Returns:
        str: Version string from setuptools_scm or fallback version.

    The version is dynamically determined by setuptools_scm from git tags.
    If git tags are not available, falls back to 0.1.0.
    """
    try:
        return version("getit-cli")
    except PackageNotFoundError:
        # Package not installed, fallback to default
        return "0.1.0"


__version__ = __set_git_version__()
__author__ = "getit contributors"

__all__ = ["__version__", "Settings"]
