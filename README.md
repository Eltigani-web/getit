<h1 align="center">getit</h1>

<p align="center">
  <strong>Universal file hosting downloader with a beautiful Terminal UI</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/getit-cli/"><img src="https://img.shields.io/pypi/v/getit-cli?color=blue&label=PyPI" alt="PyPI"></a>
  <a href="https://github.com/Eltigani-web/getit/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPLv3"></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/Eltigani-web/getit/actions"><img src="https://github.com/Eltigani-web/getit/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

<p align="center">
  Download files from GoFile, PixelDrain, MediaFire, 1Fichier, and Mega.nz with a single command.
</p>

---

## 🌟 Why GetIt?

GetIt transforms the mundane task of downloading files from various hosting services into a seamless, visual experience. Whether you are a casual user wanting a simple download or a power user needing batch processing and encryption support, GetIt handles it all with style.

## ✨ Features

- **Broad Host Support**: Seamlessly download from **GoFile**, **PixelDrain**, **MediaFire**, **1Fichier**, and **Mega.nz**.
- **Stunning TUI**: innovative terminal interface that provides real-time progress visualization, speed metrics, and active management.
- **Robust CLI**: Complete command-line control for scripting and headless operations.
- **Performance First**:
    - **Concurrent Downloads**: Maximize bandwidth by downloading multiple files at once.
    - **Smart Resume**: Automatically resumes interrupted downloads where possible.
    - **Speed Limiting**: strict bandwidth controls for background usage.
- **Advanced Capabilities**:
    - **Recursive Folder Support**: Downloads entire directory structures.
    - **Security**: Handles password-protected links and fully decrypts Mega.nz AES-CTR encryptions.
    - **Integrity**: Auto-verifies MD5/SHA256 checksums to ensure file safety.
- **Cross-Platform**: Runs flawlessly on macOS, Linux, and Windows.

## 🚀 Quick Start

### Installation

Install via pip (recommended):

```bash
pip install getit-cli
```

Or using Homebrew (macOS/Linux):

```bash
brew tap ahmedeltigani/getit
brew install getit
```

### Basic Usage

**Download a single file:**
```bash
getit download https://gofile.io/d/abc123
```

**Launch the interactive TUI:**
```bash
getit tui
```

**Batch download from a file:**
```bash
getit download -f urls.txt
```

## 📖 Comprehensive Guide

### Command Line Interface

The CLI is designed for efficiency.

```bash
getit download <URL> [OPTIONS]
```

**Common Options:**
- `-o, --output DIR`: Specify target directory (default: `./downloads`).
- `-c, --concurrent NUM`: Set max simultaneous downloads (default: 4).
- `-p, --password TEXT`: Provide password for protected resources.
- `-l, --limit SPEED`: Set a speed cap (e.g., `1M`, `500K`).
- `--no-resume`: Force restart of downloads.

### Interactive TUI Controls

Manage your queue effortlessly with keyboard shortcuts:

| Key | Action | Description |
|-----|--------|-------------|
| `a` | Add URL | Input a new URL to download queue |
| `b` | Batch Import | Load multiple URLs from a file |
| `p` | Pause/Resume | Toggle state of selected download |
| `c` | Cancel | Stop and remove selected download |
| `s` | Settings | Configure global preferences |
| `d` | Dark Mode | Toggle visual theme |
| `q` | Quit | Exit the application |

### Host Specifics

| Host | Files | Folders | Password | Encryption | Notes |
|------|:-----:|:-------:|:--------:|:----------:|-------|
| **GoFile** | ✅ | ✅ | ✅ | - | Handles rate limits & guest tokens automatically. |
| **PixelDrain** | ✅ | ✅ | - | - | Supports lists and individual files. |
| **1Fichier** | ✅ | - | ✅ | - | Manages wait times between downloads. |
| **Mega.nz** | ✅ | ✅ | - | ✅ | Features full client-side decryption. |

### Configuration

GetIt looks for `config.json` in:
- **macOS**: `~/Library/Application Support/getit/`
- **Linux**: `~/.config/getit/`
- **Windows**: `%APPDATA%\getit\`

**Example `config.json`:**
```json
{
  "download_dir": "~/Downloads/getit",
  "max_concurrent_downloads": 4,
  "enable_resume": true,
  "gofile_token": "your_token_here"
}
```

## 🛠 Development

We welcome contributions!

1. **Clone**: `git clone https://github.com/ahmedeltigani/getit.git`
2. **Setup**: `pip install -e ".[dev]"`
3. **Test**: `pytest`

### Architecture Overview

- **`core/downloader.py`**: Async engine handling HTTP streams and decryption.
- **`core/manager.py`**: Semaphore-based orchestrator for concurrency.
- **`extractors/`**: Modular logic for each file host.
- **`tui/app.py`**: Textual-based interface implementation.

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/ahmedeltigani">Ahmed Eltigani</a>
</p>
