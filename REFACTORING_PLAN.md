# Refactoring Plan - getit Codebase

## Overview

This document outlines a comprehensive refactoring plan to address code quality issues identified in the audit. Issues are organized by priority with specific implementation steps.

**Total Estimated Work**: ~50 refactoring tasks across 12 files
**Estimated Line Reduction**: ~250 lines through DRY improvements
**Estimated Maintainability Improvement**: High

---

## Phase 1: CRITICAL - Monolithic Functions (Priority: Highest)

### 1.1 Refactor `downloader.py` - `download()` Method (168 → ~30 lines)

**File**: `src/getit/core/downloader.py`
**Current**: Lines 169-336 (168 lines)
**Problem**: Single method handles 8+ responsibilities

#### Step 1.1.1: Extract Header/Cookie Preparation
```python
def _prepare_request_context(self, file_info: FileInfo) -> tuple[dict[str, str], dict[str, str], str]:
    """Prepare headers, cookies, and download URL from file info."""
    headers = dict(file_info.headers) if file_info.headers else {}
    cookies = dict(file_info.cookies) if file_info.cookies else {}
    download_url = file_info.direct_url or file_info.url
    return headers, cookies, download_url
```

#### Step 1.1.2: Extract Resume Logic
```python
def _calculate_resume_position(
    self,
    temp_path: Path,
    total_size: int,
    supports_resume: bool,
    is_encrypted: bool,
    headers: dict[str, str],
) -> int:
    """Calculate resume position and update headers if resuming."""
    if is_encrypted and temp_path.exists():
        temp_path.unlink()
        return 0

    if not (self.enable_resume and temp_path.exists()):
        return 0

    resume_pos = temp_path.stat().st_size

    if total_size > 0 and resume_pos >= total_size:
        temp_path.unlink()
        return 0

    if resume_pos > 0 and supports_resume:
        headers["Range"] = f"bytes={resume_pos}-"
        return resume_pos

    return 0
```

#### Step 1.1.3: Extract Decryptor Setup
```python
def _prepare_decryptor(self, file_info: FileInfo) -> Optional[AES]:
    """Create decryptor if file is encrypted with Mega encryption."""
    is_encrypted = getattr(file_info, "encrypted", False)
    if is_encrypted and file_info.encryption_key and file_info.encryption_iv:
        return self._create_mega_decryptor(
            file_info.encryption_key, file_info.encryption_iv
        )
    return None
```

#### Step 1.1.4: Extract Cancellation Check
```python
def _is_cancelled(self, task: DownloadTask) -> bool:
    """Check if download should be cancelled."""
    return (
        self._cancel_event.is_set()
        or task.progress.status == DownloadStatus.CANCELLED
    )
```

#### Step 1.1.5: Extract Pause Handler
```python
async def _handle_pause(self, task: DownloadTask) -> bool:
    """Handle pause state, returns False if cancelled during pause."""
    while task.progress.status == DownloadStatus.PAUSED:
        await asyncio.sleep(0.1)
        if task.progress.status == DownloadStatus.CANCELLED:
            return False
    return True
```

#### Step 1.1.6: Extract Speed Limiter
```python
async def _apply_speed_limit(self, chunk_len: int, current_speed: float) -> None:
    """Apply speed limiting delay if configured."""
    if not self.speed_limit or current_speed <= self.speed_limit:
        return
    
    target_time = chunk_len / self.speed_limit
    actual_time = chunk_len / current_speed if current_speed > 0 else 0
    delay = target_time - actual_time
    
    if delay > 0:
        await asyncio.sleep(delay)
```

#### Step 1.1.7: Extract Chunk Download Loop
```python
async def _download_chunks(
    self,
    task: DownloadTask,
    response: aiohttp.ClientResponse,
    file_handle: aiofiles.threadpool.binary.AsyncBufferedIOBase,
    decryptor: Optional[AES],
    on_progress: Optional[ProgressCallback],
) -> bool:
    """Download file chunks with progress tracking."""
    last_update_time = asyncio.get_event_loop().time()
    bytes_since_update = 0
    chunk_iter = response.content.iter_chunked(self.chunk_size)

    while True:
        chunk = await self._get_next_chunk(task, chunk_iter)
        if chunk is None:
            break
        if chunk is False:
            return False

        if self._is_cancelled(task):
            task.progress.status = DownloadStatus.CANCELLED
            return False

        if not await self._handle_pause(task):
            return False

        if decryptor:
            chunk = decryptor.decrypt(chunk)

        await file_handle.write(chunk)
        
        bytes_since_update, last_update_time = self._update_progress_if_needed(
            task, len(chunk), bytes_since_update, last_update_time, on_progress
        )

        await self._apply_speed_limit(len(chunk), task.progress.speed)

    return True
```

#### Step 1.1.8: Extract Chunk Retrieval with Timeout
```python
async def _get_next_chunk(
    self,
    task: DownloadTask,
    chunk_iter: AsyncIterator[bytes],
) -> Optional[bytes | bool]:
    """Get next chunk with timeout. Returns None for end, False for error."""
    try:
        async with asyncio.timeout(self.chunk_timeout):
            return await chunk_iter.__anext__()
    except StopAsyncIteration:
        return None
    except TimeoutError:
        task.progress.status = DownloadStatus.FAILED
        task.progress.error = f"Chunk download timed out after {self.chunk_timeout}s"
        return False
```

#### Step 1.1.9: Refactored Main Download Method
```python
async def download(
    self,
    task: DownloadTask,
    on_progress: Optional[ProgressCallback] = None,
) -> bool:
    """Download a file with resume support, encryption, and progress tracking."""
    self._cancel_event.clear()
    file_info = task.file_info
    output_path = task.output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_suffix(output_path.suffix + ".part")

    try:
        task.progress.status = DownloadStatus.DOWNLOADING
        headers, cookies, download_url = self._prepare_request_context(file_info)
        
        file_size, supports_resume, _ = await self.http.get_file_info(
            download_url, headers=file_info.headers
        )
        if file_size > 0:
            task.progress.total = file_size

        self._check_disk_space(output_path.parent, task.progress.total)
        
        decryptor = self._prepare_decryptor(file_info)
        is_encrypted = decryptor is not None
        
        resume_pos = self._calculate_resume_position(
            temp_path, task.progress.total, supports_resume, is_encrypted, headers
        )
        task.progress.downloaded = resume_pos

        success = await self._perform_download(
            task, temp_path, output_path, download_url,
            headers, cookies, resume_pos, decryptor, on_progress
        )
        
        if not success:
            return False

        return await self._finalize_download(task, file_info, output_path, temp_path, on_progress)

    except asyncio.CancelledError:
        return self._handle_cancellation(task, temp_path)
    except ChecksumMismatchError as e:
        return self._handle_checksum_error(task, e, output_path)
    except Exception as e:
        return self._handle_download_error(task, e)
```

---

### 1.2 Refactor `onefichier.py` - `_parse_page()` Method (67 → ~25 lines)

**File**: `src/getit/extractors/onefichier.py`
**Current**: Lines 109-175 (67 lines)

#### Step 1.2.1: Extract Error Checking
```python
def _check_page_errors(self, html: str, password: Optional[str]) -> None:
    """Check for error conditions in the page HTML."""
    if self.TEMP_OFFLINE_PATTERN.search(html):
        raise ExtractorError("Service temporarily unavailable or maintenance")
    if self.PREMIUM_ONLY_PATTERN.search(html):
        raise ExtractorError("Premium account required for this file")
    if self.DL_LIMIT_PATTERN.search(html):
        raise ExtractorError("Download limit reached, try again later")
```

#### Step 1.2.2: Extract Password Check
```python
def _check_password_required(self, soup: BeautifulSoup, html: str, password: Optional[str]) -> None:
    """Check if password is required but not provided."""
    if "password" in html.lower() and not password:
        password_input = soup.find("input", {"name": "pass"})
        if password_input:
            raise PasswordRequired()
```

#### Step 1.2.3: Extract Wait Handler
```python
async def _handle_wait_time(self, html: str) -> None:
    """Handle countdown wait time if present."""
    wait_match = self.WAIT_PATTERN.search(html)
    if not wait_match:
        return
    
    wait_time = int(wait_match.group(1))
    context = html.lower()[wait_match.start():wait_match.end() + 20]
    if "minute" in context:
        wait_time *= 60
    
    if 0 < wait_time < 300:
        await asyncio.sleep(wait_time + 1)
```

#### Step 1.2.4: Extract Link Finder
```python
def _find_direct_link(self, soup: BeautifulSoup, html: str) -> Optional[str]:
    """Find direct download link from page."""
    link_tag = soup.find("a", {"class": "ok"})
    if link_tag:
        href = link_tag.get("href")
        if href:
            return href

    link_match = re.search(
        r'href=["\']?(https?://[^"\'>\\s]+\\.1fichier\\.com[^"\'>\\s]*)',
        html,
    )
    return link_match.group(1) if link_match else None
```

#### Step 1.2.5: Extract Filename Finder
```python
def _find_filename(self, soup: BeautifulSoup) -> str:
    """Extract filename from page."""
    filename_tag = soup.find("td", {"class": "normal"})
    if filename_tag:
        return filename_tag.get_text(strip=True)

    title_tag = soup.find("title")
    if title_tag:
        title_text = title_tag.get_text()
        if " - " in title_text:
            return title_text.split(" - ")[0].strip()

    return "unknown"
```

---

### 1.3 Refactor `gofile.py` - `_get_content()` Method (68 → ~35 lines)

**File**: `src/getit/extractors/gofile.py`
**Current**: Lines 93-160 (68 lines)

#### Step 1.3.1: Extract Status Error Mapper
```python
_STATUS_ERRORS: ClassVar[dict[str, tuple[type[Exception], str]]] = {
    "error-notFound": (NotFound, "Content not found"),
    "error-passwordRequired": (PasswordRequired, ""),
    "error-expiredContent": (NotFound, "Content has expired"),
    "error-disabledAccount": (ExtractorError, "Account has been disabled"),
    "error-bannedAccount": (ExtractorError, "Account has been banned"),
    "error-overloaded": (ExtractorError, "Server overloaded, try again later"),
}

def _handle_status_error(self, status: str, content_id: str) -> None:
    """Raise appropriate exception for error status codes."""
    if status in ("error-wrongToken", "error-tokenInvalid"):
        return  # Handled by retry logic
    
    if status in self._STATUS_ERRORS:
        exc_class, message = self._STATUS_ERRORS[status]
        if exc_class == NotFound and not message:
            raise NotFound(f"Content {content_id} not found")
        elif exc_class == PasswordRequired:
            raise PasswordRequired()
        else:
            raise exc_class(message)
    
    if status != "ok":
        raise ExtractorError(f"API error: {status}")
```

#### Step 1.3.2: Extract Token Invalidation
```python
def _invalidate_tokens(self) -> None:
    """Invalidate all cached tokens."""
    self._token = None
    self._token_expiry = 0
    self._website_token = None
    self._website_token_expiry = 0
```

---

### 1.4 Refactor `mega.py` - `_get_folder_contents()` Method (49 → ~30 lines)

**File**: `src/getit/extractors/mega.py`
**Current**: Lines 173-221 (49 lines)

#### Step 1.4.1: Extract Key XOR Helper (Eliminates 3x Duplication)
```python
def _derive_key(self, key_a32: list[int]) -> list[int]:
    """Derive decryption key by XORing first and second halves."""
    if len(key_a32) == 8:
        return [
            key_a32[0] ^ key_a32[4],
            key_a32[1] ^ key_a32[5],
            key_a32[2] ^ key_a32[6],
            key_a32[3] ^ key_a32[7],
        ]
    return key_a32[:4]
```

#### Step 1.4.2: Extract File Item Parser
```python
def _parse_folder_item(
    self, item: dict[str, Any], master_key: list[int]
) -> Optional[dict[str, Any]]:
    """Parse a single file item from folder contents."""
    if item.get("t") != 0:
        return None

    try:
        encrypted_key = str_to_a32(base64_url_decode(item["k"].split(":")[1]))
        file_key = decrypt_key(encrypted_key, master_key)
        file_key = self._derive_key(file_key)

        attr_data = base64_url_decode(item["a"])
        attr = decrypt_attr(attr_data, file_key[:4])

        return {
            "id": item["h"],
            "name": attr.get("n", "unknown"),
            "size": item.get("s", 0),
            "key": file_key,
            "parent_id": item.get("p"),
        }
    except Exception:
        return None
```

---

### 1.5 Refactor `app.py` - `_add_download()` Method (65 → ~25 lines)

**File**: `src/getit/tui/app.py`
**Current**: Lines 821-885 (65 lines)

#### Step 1.5.1: Extract Table Row Addition
```python
def _add_task_to_table(self, task: DownloadTask, file_info: FileInfo) -> None:
    """Add a download task as a row in the downloads table."""
    table = self.query_one("#downloads-table", DataTable)
    
    filename_width = 32 if self._term_width >= 100 else 20
    truncated_name = file_info.filename[:filename_width]
    if len(file_info.filename) > filename_width:
        truncated_name += "..."

    initial_bar = f"[{PROGRESS_EMPTY * 10}]   0.0%"
    pending_status = Text("Pending", style="dim")
    
    row_data = self._build_row_data(
        truncated_name, file_info.size, initial_bar, pending_status
    )
    table.add_row(*row_data, key=task.task_id)
```

#### Step 1.5.2: Extract Row Data Builder
```python
def _build_row_data(
    self,
    filename: str,
    size: int,
    progress: str,
    status: Text,
) -> tuple:
    """Build row data tuple based on terminal width."""
    if self._term_width >= 100:
        return (filename, format_size(size), progress, "-", "-", status)
    elif self._term_width >= 80:
        return (filename, format_size(size), progress, "-", status)
    else:
        return (filename, progress, status)
```

---

## Phase 2: HIGH - DRY Violations (Priority: High)

### 2.1 Create Shared Size Parser Utility

**File**: `src/getit/extractors/base.py` (add to existing)
**Eliminates duplication in**: `mediafire.py`, `onefichier.py`

```python
SIZE_MULTIPLIERS: dict[str, int] = {
    "B": 1,
    "KB": 1024, "KO": 1024, "K": 1024,
    "MB": 1024**2, "MO": 1024**2, "M": 1024**2,
    "GB": 1024**3, "GO": 1024**3, "G": 1024**3,
    "TB": 1024**4, "TO": 1024**4, "T": 1024**4,
}

SIZE_PATTERN = re.compile(r"([\d.]+)\s*(KB|MB|GB|TB|Ko|Mo|Go|To|K|M|G|T|B)?", re.I)

def parse_size_string(text: str) -> int:
    """Parse a human-readable size string into bytes.
    
    Examples:
        "1.5 GB" -> 1610612736
        "500 MB" -> 524288000
        "100Ko" -> 102400
    """
    match = SIZE_PATTERN.search(text)
    if not match:
        return 0
    
    value = float(match.group(1))
    unit = (match.group(2) or "B").upper()
    
    # Normalize French units
    if unit.endswith("O"):
        unit = unit[:-1] + "B"
    
    multiplier = SIZE_MULTIPLIERS.get(unit, 1)
    return int(value * multiplier)
```

**Update mediafire.py** (lines 86-95):
```python
# Before:
size_span = soup.find("span", {"class": "dl-info"})
if size_span:
    size_text = size_span.get_text()
    size_match = re.search(r"([\d.]+)\s*(KB|MB|GB)", size_text, re.I)
    if size_match:
        value = float(size_match.group(1))
        unit = size_match.group(2).upper()
        multipliers = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
        size = int(value * multipliers.get(unit, 1))

# After:
size_span = soup.find("span", {"class": "dl-info"})
size = parse_size_string(size_span.get_text()) if size_span else 0
```

**Update onefichier.py** (lines 161-173):
```python
# Before: 13 lines of size parsing

# After:
size = parse_size_string(html)
```

---

### 2.2 Create Task Selection Helper in TUI

**File**: `src/getit/tui/app.py`
**Eliminates duplication in**: 4 action methods

```python
def _get_selected_task(self) -> Optional[DownloadTask]:
    """Get the currently selected task from the downloads table.
    
    Returns None if no row is selected or task not found.
    """
    table = self.query_one("#downloads-table", DataTable)
    if table.cursor_row is None:
        return None
    
    try:
        row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        task_id = str(row_key.value)
        return self.tasks.get(task_id)
    except Exception:
        return None
```

**Update action_cancel_selected** (lines 901-910):
```python
# Before: 10 lines

# After:
def action_cancel_selected(self) -> None:
    """Cancel the currently selected download."""
    task = self._get_selected_task()
    if task:
        task.progress.status = DownloadStatus.CANCELLED
```

**Update action_pause_resume_selected** (lines 912-927):
```python
# Before: 16 lines

# After:
def action_pause_resume_selected(self) -> None:
    """Toggle pause/resume on the currently selected download."""
    task = self._get_selected_task()
    if not task:
        return
    
    if task.progress.status == DownloadStatus.DOWNLOADING:
        task.progress.status = DownloadStatus.PAUSED
        self.notify(f"Paused: {task.file_info.filename[:30]}")
    elif task.progress.status == DownloadStatus.PAUSED:
        task.progress.status = DownloadStatus.DOWNLOADING
        self.notify(f"Resumed: {task.file_info.filename[:30]}")
```

**Update action_retry_selected** (lines 944-962):
```python
# Before: 19 lines

# After:
def action_retry_selected(self) -> None:
    """Retry a failed or cancelled download."""
    task = self._get_selected_task()
    if not task:
        return
    
    if task.progress.status in (DownloadStatus.FAILED, DownloadStatus.CANCELLED):
        task.progress.status = DownloadStatus.PENDING
        task.progress.error = None
        task.retries = 0
        self._start_download(task)
        self.notify(f"Retrying: {task.file_info.filename[:30]}")
```

---

### 2.3 Create Base Modal Screen Class

**File**: `src/getit/tui/app.py` (add before other screens)
**Eliminates duplication in**: 4 modal screen classes

```python
class BaseModalScreen(ModalScreen[Optional[Any]]):
    """Base class for modal screens with common cancel behavior."""
    
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]
    
    def action_cancel(self) -> None:
        """Dismiss the screen without a result."""
        self.dismiss(None)
    
    def _on_cancel_button(self) -> None:
        """Handle cancel button press."""
        self.dismiss(None)
```

**Update BatchFileScreen**:
```python
class BatchFileScreen(BaseModalScreen[Optional[tuple[str, Optional[str], Optional[str]]]]):
    # Remove: BINDINGS definition (inherited)
    # Remove: action_cancel method (inherited)
    # Update on_cancel to call self._on_cancel_button()
```

**Same pattern for**: `AddUrlScreen`, `ErrorDetailsScreen`, `SettingsScreen`

---

### 2.4 Create Status Counter Helper

**File**: `src/getit/tui/app.py`
**Eliminates duplication in**: `_update_status_bar()`

```python
def _count_tasks_by_status(self, *statuses: DownloadStatus) -> int:
    """Count tasks matching any of the given statuses."""
    return sum(
        1 for t in self.tasks.values()
        if t.progress.status in statuses
    )

def _get_status_summary(self) -> dict[str, int | float]:
    """Get summary of task counts and total speed."""
    return {
        "total": len(self.tasks),
        "active": self._count_tasks_by_status(DownloadStatus.DOWNLOADING),
        "completed": self._count_tasks_by_status(DownloadStatus.COMPLETED),
        "failed": self._count_tasks_by_status(DownloadStatus.FAILED),
        "speed": sum(t.progress.speed for t in self.tasks.values()),
    }
```

---

### 2.5 Create Download Result Factory

**File**: `src/getit/core/manager.py`
**Eliminates duplication in**: `download_task()`, `download_urls()`

```python
def _create_result(
    self,
    task: DownloadTask,
    success: bool,
    error: Optional[str] = None,
) -> DownloadResult:
    """Create a download result with consistent structure."""
    return DownloadResult(
        task=task,
        success=success,
        error=error or task.progress.error,
    )

def _create_error_result(self, url: str, error: Exception) -> DownloadResult:
    """Create a download result for a failed URL extraction."""
    dummy_task = DownloadTask(
        file_info=FileInfo(url=url, filename="error"),
        output_path=Path("error"),
    )
    dummy_task.progress.status = DownloadStatus.FAILED
    dummy_task.progress.error = str(error)
    return self._create_result(dummy_task, success=False, error=str(error))
```

---

## Phase 3: MEDIUM - Deep Nesting Reduction

### 3.1 Flatten `_import_from_file()` with Early Returns

**File**: `src/getit/tui/app.py`
**Current nesting**: 4-5 levels

```python
@work(exclusive=False)
async def _import_from_file(
    self,
    file_path: str,
    password: Optional[str] = None,
    custom_folder: Optional[str] = None,
) -> None:
    """Import URLs from a text file for batch downloading."""
    path = Path(file_path)
    
    # Early return validations (flatten nesting)
    if not path.exists():
        self.notify(f"File not found: {file_path}", severity="error")
        return

    if not path.is_file():
        self.notify(f"Not a file: {file_path}", severity="error")
        return

    urls = self._parse_urls_from_file(path)
    if not urls:
        self.notify("No valid URLs found in file", severity="warning")
        return

    batch_output_dir = await self._prepare_batch_folder(custom_folder)
    if batch_output_dir is False:  # Explicit failure
        return

    await self._process_url_batch(urls, password, batch_output_dir)
```

**Extract helper methods**:
```python
def _parse_urls_from_file(self, path: Path) -> list[str]:
    """Parse valid URLs from a text file."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    return [
        line.strip() for line in lines
        if line.strip() 
        and not line.strip().startswith("#")
        and line.strip().startswith("http")
    ]

async def _prepare_batch_folder(self, custom_folder: Optional[str]) -> Optional[Path | bool]:
    """Prepare output folder for batch import. Returns False on failure."""
    if not custom_folder:
        return None
    
    base_folder = self.settings.download_dir / custom_folder
    batch_output_dir = self._get_unique_folder(base_folder)
    
    try:
        batch_output_dir.mkdir(parents=True, exist_ok=True)
        self.notify(f"Saving to: {batch_output_dir.name}")
        return batch_output_dir
    except OSError as e:
        self.notify(f"Failed to create folder: {e}", severity="error")
        return False

async def _process_url_batch(
    self,
    urls: list[str],
    password: Optional[str],
    output_dir: Optional[Path],
) -> None:
    """Process a batch of URLs for downloading."""
    self.notify(f"Importing {len(urls)} URL(s)...")
    
    success_count = 0
    for url in urls:
        try:
            await self._add_download(url, password, output_dir)
            success_count += 1
        except Exception:
            pass  # TODO: Log error

    severity = "information" if success_count > 0 else "warning"
    self.notify(f"Imported {success_count}/{len(urls)} URL(s)", severity=severity)
```

---

### 3.2 Flatten `on_mount()` Column Configuration

**File**: `src/getit/tui/app.py`
**Current nesting**: 3-4 levels in if/elif chain

```python
def _get_column_config(self) -> list[tuple[str, int]]:
    """Get column configuration based on terminal width."""
    if self._term_width >= 120:
        return [
            ("Filename", 40), ("Size", 12), ("Progress", 22),
            ("Speed", 12), ("ETA", 10), ("Status", 12),
        ]
    elif self._term_width >= 100:
        return [
            ("Filename", 35), ("Size", 12), ("Progress", 20),
            ("Speed", 12), ("ETA", 10), ("Status", 12),
        ]
    elif self._term_width >= 80:
        return [
            ("Filename", 25), ("Size", 10), ("Progress", 18),
            ("Speed", 10), ("Status", 10),
        ]
    else:
        return [("File", 20), ("Progress", 15), ("Status", 10)]

def _setup_table_columns(self, table: DataTable) -> None:
    """Configure table columns based on terminal width."""
    for name, width in self._get_column_config():
        self._datatable_column_keys[name] = table.add_column(name, width=width)
```

---

## Phase 4: Documentation (Priority: Medium-Low)

### 4.1 Add Class Docstrings

**All extractor classes need docstrings:**

```python
class GoFileExtractor(BaseExtractor):
    """Extract download links from GoFile.io.
    
    Handles both files and folders, supports password-protected content,
    and manages guest token authentication automatically.
    
    Attributes:
        API_URL: Base URL for GoFile API
        EXTRACTOR_NAME: Identifier used in FileInfo
    """
```

```python
class FileDownloader:
    """Download files with resume support, encryption, and progress tracking.
    
    Features:
        - Resume interrupted downloads (if server supports Range requests)
        - Mega.nz AES-CTR decryption
        - Speed limiting
        - Checksum verification (MD5, SHA1, SHA256, SHA512)
        - Progress callbacks
    
    Attributes:
        http: HTTP client for making requests
        chunk_size: Size of download chunks in bytes
        enable_resume: Whether to attempt resuming partial downloads
        speed_limit: Maximum download speed in bytes/second (None for unlimited)
    """
```

```python
class DownloadManager:
    """Orchestrate concurrent downloads from multiple file hosting services.
    
    Manages extractors, download tasks, and concurrent download limits.
    Provides high-level API for downloading URLs with automatic host detection.
    
    Example:
        async with DownloadManager(output_dir=Path("./downloads")) as manager:
            results = await manager.download_url("https://gofile.io/d/abc123")
    """
```

### 4.2 Add Method Docstrings Template

All public methods should follow this format:

```python
async def download(
    self,
    task: DownloadTask,
    on_progress: Optional[ProgressCallback] = None,
) -> bool:
    """Download a file with resume support and progress tracking.
    
    Args:
        task: Download task containing file info and output path
        on_progress: Optional callback invoked every 0.5 seconds with progress
    
    Returns:
        True if download completed successfully, False otherwise
    
    Raises:
        OSError: If insufficient disk space
        ChecksumMismatchError: If checksum verification fails
    """
```

---

## Phase 5: Exception Handling (Priority: Low)

### 5.1 Replace Bare Exception Suppression

**Add logging and specific exception types:**

```python
import logging

logger = logging.getLogger(__name__)

# Before:
except Exception:
    pass

# After (for non-critical errors):
except (KeyError, ValueError) as e:
    logger.debug(f"Failed to update table cell for {task_id}: {e}")

# After (for potentially important errors):
except Exception as e:
    logger.warning(f"Unexpected error processing task {task_id}: {e}", exc_info=True)
```

### 5.2 Create Exception Hierarchy

**File**: `src/getit/core/exceptions.py` (new file)

```python
"""Custom exceptions for getit."""

class GetItError(Exception):
    """Base exception for all getit errors."""
    pass

class DownloadError(GetItError):
    """Error during file download."""
    pass

class ExtractionError(GetItError):
    """Error extracting file info from URL."""
    pass

class DiskSpaceError(DownloadError):
    """Insufficient disk space for download."""
    pass

class ResumeError(DownloadError):
    """Error resuming partial download."""
    pass
```

---

## Implementation Order

### Week 1: Critical Path
1. [ ] 1.1 - Refactor `downloader.py` `download()` method
2. [ ] 2.1 - Create shared size parser utility
3. [ ] 2.2 - Create task selection helper in TUI

### Week 2: High Priority DRY
4. [ ] 1.4 - Refactor `mega.py` with key XOR helper
5. [ ] 2.3 - Create base modal screen class
6. [ ] 2.4 - Create status counter helper
7. [ ] 2.5 - Create download result factory

### Week 3: Medium Priority
8. [ ] 1.2 - Refactor `onefichier.py` `_parse_page()`
9. [ ] 1.3 - Refactor `gofile.py` `_get_content()`
10. [ ] 3.1 - Flatten `_import_from_file()`
11. [ ] 3.2 - Flatten `on_mount()` column configuration

### Week 4: Documentation & Cleanup
12. [ ] 4.1 - Add class docstrings
13. [ ] 4.2 - Add method docstrings
14. [ ] 5.1 - Replace bare exception suppression
15. [ ] 5.2 - Create exception hierarchy
16. [ ] 1.5 - Refactor `app.py` `_add_download()`

---

## Verification Checklist

After each refactoring step:

- [ ] Run test suite: `uv run pytest tests/ -v`
- [ ] Check type errors: `uv run mypy src/getit/ --ignore-missing-imports`
- [ ] Verify TUI works: `uv run getit tui`
- [ ] Test a real download: `uv run getit download "<test_url>"`
- [ ] Check import succeeds: `python -c "from getit.tui.app import GetItApp"`

---

## Metrics to Track

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Longest function | 168 lines | < 40 lines |
| Max nesting depth | 5 levels | 3 levels |
| Duplicate code blocks | 15+ | 0 |
| Documented classes | 0% | 100% |
| Documented public methods | 0% | 100% |
| Bare `except: pass` | 6 | 0 |
