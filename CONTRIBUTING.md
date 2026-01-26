# Contributing to getit

First off, thank you for considering contributing to getit! It's people like you that make getit such a great tool.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [How to Contribute](#how-to-contribute)
- [Adding a New Extractor](#adding-a-new-extractor)
- [Testing](#testing)
- [Style Guidelines](#style-guidelines)
- [Pull Request Process](#pull-request-process)

## Code of Conduct

This project and everyone participating in it is governed by our Code of Conduct. By participating, you are expected to uphold this code. Please be respectful and constructive in all interactions.

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- A GitHub account

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/getit.git
cd getit
```

3. Add the upstream repository:

```bash
git remote add upstream https://github.com/yourusername/getit.git
```

## Development Setup

### Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

### Install Dependencies

```bash
# Install package in editable mode with dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Verify Installation

```bash
# Run the CLI
getit --help

# Run tests
pytest

# Run linter
ruff check src/
```

## Project Structure

```
getit/
├── src/getit/
│   ├── __init__.py          # Package version and exports
│   ├── __main__.py          # Entry point for python -m getit
│   ├── cli.py               # CLI commands (Typer)
│   ├── config.py            # Configuration management (Pydantic)
│   │
│   ├── core/                # Core download functionality
│   │   ├── downloader.py    # Single file downloader
│   │   └── manager.py       # Download orchestration
│   │
│   ├── extractors/          # Host-specific extractors
│   │   ├── base.py          # Base classes and interfaces
│   │   ├── gofile.py
│   │   ├── pixeldrain.py
│   │   ├── mediafire.py
│   │   ├── onefichier.py
│   │   └── mega.py
│   │
│   ├── storage/             # Data persistence
│   │   └── history.py       # Download history (SQLite)
│   │
│   ├── tui/                 # Terminal UI
│   │   └── app.py           # Textual application
│   │
│   └── utils/               # Shared utilities
│       └── http.py          # HTTP client wrapper
│
├── tests/                   # Test suite
│   ├── conftest.py          # Pytest fixtures
│   ├── test_extractors.py
│   ├── test_downloader.py
│   └── test_cli.py
│
├── pyproject.toml           # Package configuration
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

## How to Contribute

### Reporting Bugs

Before creating a bug report, please check existing issues to avoid duplicates.

When filing an issue, include:

- **Clear title** describing the problem
- **Steps to reproduce** the issue
- **Expected behavior** vs **actual behavior**
- **Environment details**: OS, Python version, getit version
- **Error messages** or logs (use code blocks)
- **URL** that caused the issue (if applicable and not private)

### Suggesting Features

Feature requests are welcome! Please include:

- **Use case**: Why do you need this feature?
- **Proposed solution**: How should it work?
- **Alternatives considered**: Other approaches you've thought of

### Code Contributions

1. Check for existing issues or create one to discuss your idea
2. Fork the repository and create a branch
3. Write your code and tests
4. Ensure all tests pass
5. Submit a pull request

## Adding a New Extractor

This is the most common type of contribution. Here's a complete guide:

### Step 1: Create the Extractor File

Create `src/getit/extractors/newhost.py`:

```python
from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar, Optional

from getit.extractors.base import (
    BaseExtractor,
    ExtractorError,
    FileInfo,
    FolderInfo,
    NotFound,
    PasswordRequired,
)

if TYPE_CHECKING:
    from getit.utils.http import HTTPClient


class NewHostExtractor(BaseExtractor):
    """Extractor for newhost.com file hosting service."""
    
    # Required class attributes
    SUPPORTED_DOMAINS: ClassVar[tuple[str, ...]] = ("newhost.com", "newhost.io")
    EXTRACTOR_NAME: ClassVar[str] = "newhost"
    URL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"https?://(?:www\.)?newhost\.(?:com|io)/(?:file/)?(?P<id>[a-zA-Z0-9]+)"
    )

    def __init__(self, http_client: HTTPClient):
        super().__init__(http_client)
        # Add any instance-specific state here

    async def extract(
        self, url: str, password: Optional[str] = None
    ) -> list[FileInfo]:
        """
        Extract file information from URL.
        
        Args:
            url: The URL to extract from
            password: Optional password for protected content
            
        Returns:
            List of FileInfo objects
            
        Raises:
            NotFound: If content doesn't exist
            PasswordRequired: If password is needed but not provided
            ExtractorError: For other errors
        """
        file_id = self.extract_id(url)
        if not file_id:
            raise ExtractorError(f"Could not extract file ID from {url}")

        # Fetch file metadata from API or HTML
        # This is where host-specific logic goes
        
        return [
            FileInfo(
                url=url,
                filename="example.zip",
                size=1024000,
                direct_url="https://download.newhost.com/file/...",
                extractor_name=self.EXTRACTOR_NAME,
                # Optional fields:
                checksum="abc123...",
                checksum_type="md5",
                headers={"Authorization": "Bearer ..."},
                cookies={"session": "..."},
            )
        ]

    async def extract_folder(
        self, url: str, password: Optional[str] = None
    ) -> Optional[FolderInfo]:
        """Extract folder contents. Return None if not a folder URL."""
        # Implement if the host supports folders
        return None
```

### Step 2: Register the Extractor

Edit `src/getit/core/manager.py`:

```python
from getit.extractors.newhost import NewHostExtractor

# Add to EXTRACTORS list
EXTRACTORS = [
    GoFileExtractor,
    PixelDrainExtractor,
    MediaFireExtractor,
    OneFichierExtractor,
    MegaExtractor,
    NewHostExtractor,  # Add here
]
```

### Step 3: Write Tests

Create `tests/test_newhost.py`:

```python
import pytest
from getit.extractors.newhost import NewHostExtractor


class TestNewHostExtractor:
    def test_can_handle_valid_url(self):
        assert NewHostExtractor.can_handle("https://newhost.com/file/abc123")
        assert NewHostExtractor.can_handle("https://www.newhost.io/xyz789")

    def test_cannot_handle_invalid_url(self):
        assert not NewHostExtractor.can_handle("https://example.com/file")
        assert not NewHostExtractor.can_handle("https://gofile.io/d/abc")

    def test_extract_id(self):
        assert NewHostExtractor.extract_id("https://newhost.com/file/abc123") == "abc123"

    @pytest.mark.asyncio
    async def test_extract_file(self, http_client):
        extractor = NewHostExtractor(http_client)
        # Use VCR or mock responses for testing
        files = await extractor.extract("https://newhost.com/file/test123")
        assert len(files) == 1
        assert files[0].filename == "expected_name.zip"
```

### Step 4: Update Documentation

Add your host to the README.md table and any host-specific notes.

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_extractors.py

# Run specific test
pytest tests/test_extractors.py::TestGoFileExtractor::test_extract_id

# Run with coverage
pytest --cov=src/getit --cov-report=html
open htmlcov/index.html
```

### Writing Tests

- Use `pytest` and `pytest-asyncio` for async tests
- Use `aioresponses` or `vcr.py` for mocking HTTP requests
- Aim for high coverage on new code
- Test both success and error cases

### Test Fixtures

Common fixtures are in `tests/conftest.py`:

```python
@pytest.fixture
async def http_client():
    """Provide an HTTP client for tests."""
    from getit.utils.http import HTTPClient
    async with HTTPClient() as client:
        yield client
```

## Style Guidelines

### Code Style

We use `ruff` for linting and formatting:

```bash
# Format code
ruff format src/ tests/

# Check for issues
ruff check src/ tests/

# Auto-fix issues
ruff check --fix src/ tests/
```

### Type Hints

All code should be fully typed:

```python
# Good
async def download(url: str, output: Path) -> bool:
    ...

# Bad
async def download(url, output):
    ...
```

Run mypy to check types:

```bash
mypy src/
```

### Docstrings

Use Google-style docstrings:

```python
async def extract(self, url: str, password: Optional[str] = None) -> list[FileInfo]:
    """
    Extract file information from URL.
    
    Args:
        url: The URL to extract from.
        password: Optional password for protected content.
        
    Returns:
        List of FileInfo objects containing file metadata.
        
    Raises:
        NotFound: If the content doesn't exist.
        PasswordRequired: If a password is needed but not provided.
    """
```

### Commit Messages

Follow conventional commits:

```
type(scope): short description

Longer description if needed.

Fixes #123
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Formatting, no code change
- `refactor`: Code change that neither fixes a bug nor adds a feature
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(extractor): add support for newhost.com
fix(mega): handle expired links gracefully
docs(readme): add troubleshooting section
test(gofile): add tests for folder extraction
```

## Pull Request Process

### Before Submitting

1. **Update your fork:**
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks:**
   ```bash
   ruff format src/ tests/
   ruff check src/ tests/
   mypy src/
   pytest
   ```

3. **Update documentation** if needed

### Submitting

1. Push to your fork:
   ```bash
   git push origin your-branch-name
   ```

2. Open a Pull Request on GitHub

3. Fill out the PR template:
   - **Description**: What does this PR do?
   - **Related issues**: Fixes #123
   - **Type of change**: Bug fix / Feature / Docs
   - **Checklist**: Tests, docs, formatting

### After Submitting

- Respond to review feedback
- Make requested changes
- Keep your branch updated with main

### Review Process

1. Automated checks must pass (CI, linting, tests)
2. At least one maintainer review required
3. All conversations must be resolved
4. Squash and merge when approved

## Questions?

- Open a [Discussion](https://github.com/yourusername/getit/discussions) for questions
- Check existing [Issues](https://github.com/yourusername/getit/issues) for known problems
- Join our community chat (if applicable)

Thank you for contributing! 🎉
