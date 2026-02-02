"""Extractor registry for managing file host extractors."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from getit.extractors.base import BaseExtractor


class RegistrationError(Exception):
    """Raised when there's an error registering an extractor."""

    pass


class ExtractorRegistry:
    """Registry for managing file host extractors with self-registration.

    Provides decorator-based registration and URL-based lookups.
    """

    _extractors: dict[str, type[BaseExtractor]] = {}

    @classmethod
    def register(cls, extractor_cls: type[BaseExtractor]) -> type[BaseExtractor]:
        """Register an extractor via decorator.

        Args:
            extractor_cls: Extractor class to register.

        Returns:
            The extractor class (unchanged).

        Raises:
            RegistrationError: If an extractor with the same name is already registered.
        """
        name = extractor_cls.EXTRACTOR_NAME
        if name in cls._extractors:
            raise RegistrationError(
                f"Extractor '{name}' is already registered. "
                f"Cannot register {extractor_cls.__name__}."
            )
        cls._extractors[name] = extractor_cls
        return extractor_cls

    @classmethod
    def get(cls, name: str) -> type[BaseExtractor] | None:
        """Get an extractor by name.

        Args:
            name: Extractor name (EXTRACTOR_NAME).

        Returns:
            Extractor class or None if not found.
        """
        return cls._extractors.get(name)

    @classmethod
    def list(cls) -> list[type[BaseExtractor]]:
        """List all registered extractors.

        Returns:
            List of registered extractor classes.
        """
        return list(cls._extractors.values())

    @classmethod
    def get_for_url(cls, url: str) -> type[BaseExtractor] | None:
        """Find extractor that can handle a URL.

        Iterates through registered extractors and returns the first one
        whose can_handle() method returns True for the given URL.

        Args:
            url: URL to find an extractor for.

        Returns:
            Extractor class or None if no extractor can handle the URL.
        """
        for extractor in cls._extractors.values():
            if extractor.can_handle(url):
                return extractor
        return None
