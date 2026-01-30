# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Single source of truth versioning using setuptools_scm from git tags
- CHANGELOG.md to track releases and changes
- Homebrew tap for macOS/Linux package distribution
- Production readiness documentation and scorecard
- Structured logging with JSON/plain format support
- Global proxy support via HTTP(S)_PROXY and NO_PROXY
- Per-provider rate limiting and backoff
- Long-lived Docker worker with healthcheck
- Graceful shutdown handling

### Changed
- Version now dynamically determined from git tags instead of hardcoded
- Build backend configured for setuptools_scm integration
- Homebrew formula uses correct GPLv3 license (was MIT placeholder)

### Security
- Config and history files set to restrictive permissions (600)
- Secret redaction in structured logs
- SQLite WAL mode enabled with busy timeout
- Schema versioning hook for database migrations

## [0.1.0] - TBD

### Added
- Initial release of getit CLI and TUI
- Support for GoFile, PixelDrain, MediaFire, 1Fichier, and Mega.nz
- CLI with download, info, and config commands
- Interactive TUI for queue management
- Concurrent downloads with configurable limits
- Resume support for partial downloads
- Speed limiting functionality
- Password-protected file support
- Recursive folder downloads
- Mega.nz AES-CTR decryption
- MD5/SHA256 checksum verification
- Configuration file support (JSON)
- Structured logging with run/download/request IDs
- Per-host extractors with rate limiting
