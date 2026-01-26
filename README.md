<p align="center">
  <img src="https://raw.githubusercontent.com/yourusername/getit/main/assets/logo.png" alt="getit logo" width="200">
</p>

<h1 align="center">getit</h1>

<p align="center">
  <strong>Universal file hosting downloader with beautiful TUI</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/getit/"><img src="https://img.shields.io/pypi/v/getit?color=blue&label=PyPI" alt="PyPI"></a>
  <a href="https://github.com/yourusername/getit/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License: MIT"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/yourusername/getit/actions"><img src="https://img.shields.io/github/actions/workflow/status/yourusername/getit/ci.yml?branch=main" alt="CI"></a>
</p>

<p align="center">
  Download files from GoFile, PixelDrain, MediaFire, 1Fichier, and Mega.nz with a single command.
</p>

---

## Features

- **5 File Hosts** — GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz
- **Beautiful TUI** — Interactive terminal interface with real-time progress bars
- **CLI Mode** — Script-friendly command-line interface
- **Concurrent Downloads** — Download multiple files simultaneously
- **Resume Support** — Continue interrupted downloads automatically
- **Folder Support** — Download entire folders recursively
- **Password Protection** — Handle password-protected content
- **Mega.nz Encryption** — Full AES-CTR decryption support
- **Checksum Verification** — Automatic MD5/SHA256 verification
- **Speed Limiting** — Control bandwidth usage
- **Cross-Platform** — Works on macOS, Linux, and Windows

## Demo

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ getit - Universal File Downloader                                           │
├─────────────────────────────────────────────────────────────────────────────┤
│ [Add URL] [Start All] [Cancel All] [Clear Completed]                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ Filename                      │ Size     │ Progress           │ Speed      │
├───────────────────────────────┼──────────┼────────────────────┼────────────┤
│ ubuntu-24.04-desktop.iso      │ 4.7 GB   │ [████████░░] 82.3% │ 45.2 MB/s  │
│ project-files.zip             │ 156.2 MB │ [██████████] Done  │ -          │
│ backup-2024.tar.gz            │ 2.1 GB   │ [██░░░░░░░░] 23.1% │ 12.8 MB/s  │
└─────────────────────────────────────────────────────────────────────────────┘
 Downloads: 3 | Active: 2 | Completed: 1 | Speed: 58.0 MB/s
```

## Installation

### Using pip (Recommended)

```bash
pip install getit
```

### Using Homebrew (macOS/Linux)

```bash
brew tap yourusername/getit
brew install getit
```

### From Source

```bash
git clone https://github.com/yourusername/getit.git
cd getit
pip install -e .
```

## Quick Start

### Download a file

```bash
getit download https://gofile.io/d/abc123
```

### Launch the TUI

```bash
getit tui
```

### Download multiple files

```bash
getit download https://gofile.io/d/abc123 https://pixeldrain.com/u/xyz789
```

### Download from a file containing URLs

```bash
getit download -f urls.txt
```

## Usage

### CLI Commands

```bash
# Download with options
getit download <url> [options]

Options:
  -o, --output DIR       Output directory (default: ./downloads)
  -c, --concurrent NUM   Max concurrent downloads (default: 4)
  -p, --password TEXT    Password for protected content
  -l, --limit SPEED      Speed limit (e.g., 1M, 500K)
  --no-resume            Disable resume support
  --no-verify            Skip checksum verification

# Show file info without downloading
getit info <url>

# Show current configuration
getit config --show

# List supported hosts
getit supported
```

### TUI Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `a` | Add URL |
| `b` | Batch import from file |
| `p` | Pause/Resume selected |
| `c` | Cancel selected |
| `e` | View error details |
| `Space` | Retry failed download |
| `s` | Open settings |
| `d` | Toggle dark mode |
| `r` | Refresh |
| `q` | Quit |

## Supported Hosts

| Host | Files | Folders | Password | Encryption | API Key |
|------|:-----:|:-------:|:--------:|:----------:|:-------:|
| **GoFile** | ✅ | ✅ | ✅ | - | ✅ |
| **PixelDrain** | ✅ | ✅ | - | - | ✅ |
| **MediaFire** | ✅ | ✅ | - | - | - |
| **1Fichier** | ✅ | - | ✅ | - | - |
| **Mega.nz** | ✅ | ✅ | - | ✅ | - |

### Host-Specific Notes

<details>
<summary><strong>GoFile</strong></summary>

- Supports guest accounts (auto-created) or API tokens
- Handles rate limiting automatically
- Recursive folder downloads supported

```bash
# With API token
export GETIT_GOFILE_TOKEN=your_token
getit download https://gofile.io/d/abc123
```
</details>

<details>
<summary><strong>Mega.nz</strong></summary>

- Full AES-CTR decryption for encrypted files
- Supports both new (`/file/`) and legacy (`#!`) URL formats
- Folder downloads with nested structure preserved

```bash
# File URL
getit download "https://mega.nz/file/abc123#key"

# Folder URL
getit download "https://mega.nz/folder/abc123#key"
```
</details>

<details>
<summary><strong>1Fichier</strong></summary>

- Handles wait times automatically
- Supports all mirror domains (alterupload.com, dl4free.com, etc.)
- Password-protected files supported

```bash
getit download https://1fichier.com/?abc123 --password "secret"
```
</details>

## Configuration

### Config File Location

| OS | Path |
|----|------|
| macOS | `~/Library/Application Support/getit/config.json` |
| Linux | `~/.config/getit/config.json` |
| Windows | `%APPDATA%\getit\config.json` |

### Environment Variables

```bash
# Core settings
export GETIT_DOWNLOAD_DIR=~/Downloads/getit
export GETIT_MAX_CONCURRENT_DOWNLOADS=4
export GETIT_SPEED_LIMIT=0  # 0 = unlimited

# API keys
export GETIT_GOFILE_TOKEN=your_gofile_token
export GETIT_PIXELDRAIN_API_KEY=your_pixeldrain_key
```

### Config File Example

```json
{
  "download_dir": "~/Downloads/getit",
  "max_concurrent_downloads": 4,
  "speed_limit": null,
  "enable_resume": true,
  "verify_checksum": true,
  "gofile_token": null,
  "pixeldrain_api_key": null
}
```

## Architecture

```
src/getit/
├── __init__.py          # Package entry point
├── __main__.py          # python -m getit
├── cli.py               # Typer CLI interface
├── config.py            # Pydantic settings management
├── core/
│   ├── downloader.py    # Async file downloader with AES decryption
│   └── manager.py       # Concurrent download orchestration
├── extractors/
│   ├── base.py          # BaseExtractor ABC, FileInfo dataclass
│   ├── gofile.py        # GoFile with rate limiting & token refresh
│   ├── pixeldrain.py    # PixelDrain files & lists
│   ├── mediafire.py     # MediaFire API + HTML fallback
│   ├── onefichier.py    # 1Fichier with wait time handling
│   └── mega.py          # Mega.nz with full encryption support
├── storage/
│   └── history.py       # SQLite download history
├── tui/
│   └── app.py           # Textual TUI application
└── utils/
    └── http.py          # Async HTTP client with rate limiting
```

### Key Components

| Component | Description |
|-----------|-------------|
| `FileDownloader` | Handles single file downloads with resume, decryption, and checksum verification |
| `DownloadManager` | Orchestrates concurrent downloads with semaphore-based limiting |
| `BaseExtractor` | Abstract base class for all host extractors |
| `HTTPClient` | aiohttp wrapper with rate limiting, timeouts, and connection pooling |
| `GetItApp` | Textual-based TUI with real-time progress updates |

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Clone the repository
git clone https://github.com/yourusername/getit.git
cd getit

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/getit --cov-report=html

# Run specific test file
pytest tests/test_extractors.py
```

### Code Quality

```bash
# Format code
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Type checking
mypy src/
```

### Adding a New Extractor

1. Create a new file in `src/getit/extractors/`
2. Inherit from `BaseExtractor`
3. Implement required methods:

```python
from getit.extractors.base import BaseExtractor, FileInfo

class NewHostExtractor(BaseExtractor):
    SUPPORTED_DOMAINS = ("newhost.com",)
    EXTRACTOR_NAME = "newhost"
    
    async def extract(self, url: str, password: str | None = None) -> list[FileInfo]:
        # Extract file information from URL
        ...
```

4. Register in `src/getit/core/manager.py`
5. Add tests in `tests/test_extractors.py`

### Pull Request Guidelines

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit with descriptive message
6. Push to your fork
7. Open a Pull Request

### Commit Message Format

```
type: short description

Longer description if needed.

Fixes #123
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## Roadmap

- [ ] Browser extension for one-click downloads
- [ ] Download scheduling
- [ ] Bandwidth scheduling (limit during work hours)
- [ ] More extractors (Dropbox, Google Drive, etc.)
- [ ] Plugin system for custom extractors
- [ ] Web UI option
- [ ] Docker image

## Troubleshooting

### Common Issues

<details>
<summary><strong>Downloads fail with "Rate limited"</strong></summary>

Some hosts rate limit downloads. Wait a few minutes and try again, or use an API key if supported.

```bash
export GETIT_GOFILE_TOKEN=your_token
```
</details>

<details>
<summary><strong>Mega.nz files are corrupted</strong></summary>

Ensure you have the full URL including the decryption key after the `#`:

```bash
# Correct
getit download "https://mega.nz/file/abc123#decryption-key"

# Wrong - missing key
getit download "https://mega.nz/file/abc123"
```
</details>

<details>
<summary><strong>Resume not working</strong></summary>

Resume only works if:
- The server supports Range requests
- The file is not encrypted (Mega.nz)
- You haven't moved the `.part` file

</details>

### Debug Mode

```bash
# Enable verbose logging
GETIT_DEBUG=1 getit download <url>
```

## Acknowledgments

- [aiohttp](https://github.com/aio-libs/aiohttp) - Async HTTP client
- [Textual](https://github.com/Textualize/textual) - TUI framework
- [Typer](https://github.com/tiangolo/typer) - CLI framework
- [Rich](https://github.com/Textualize/rich) - Terminal formatting
- [PyCryptodome](https://github.com/Legrandin/pycryptodome) - AES encryption

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/yourusername">yourusername</a>
</p>

<p align="center">
  <a href="https://github.com/yourusername/getit/issues">Report Bug</a>
  ·
  <a href="https://github.com/yourusername/getit/issues">Request Feature</a>
  ·
  <a href="https://github.com/yourusername/getit/discussions">Discussions</a>
</p>
