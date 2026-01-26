# Audit Remediation Work Plan

## Context

### Original Request
Create a comprehensive work plan to address ALL issues identified in the codebase audit of the `getit` TUI file downloader. The audit identified 35 issues across 4 severity levels.

### Interview Summary
**Key Discussions**:
- **Priority**: Security First approach - CRITICAL → HIGH → MEDIUM → LOW
- **Testing**: TDD - Write failing tests before implementing fixes
- **TUI Refactoring**: Phased approach - modals → widgets → screens (incremental extraction)

**Research Findings**:
- Existing test infrastructure: pytest with 48 tests in `tests/`, 15 fixtures in `conftest.py`
- Test command: `uv run pytest tests/ -v`
- Coverage command: `uv run pytest tests/ --cov=src/getit --cov-report=html`
- Current coverage: ~60% on downloader, ~90% on config, 0% on extractors/manager/TUI
- Uses: aiohttp, Textual, Pydantic, aiofiles, pycryptodomex, BeautifulSoup

### Metis Review
**Identified Gaps** (addressed):
- Audit location: Comprehensive audit performed during this session (files analyzed in detail)
- TOCTOU location: `manager.py:138-140` (file existence check race)
- TUI boundaries: `app.py` only (1021 lines), extract to `tui/screens/` and `tui/widgets/`
- 1Fichier blocking: Code-fixable via `asyncio.wait_for()` with timeout/callback pattern
- Dependencies: Most issues are independent; analyzed and sequenced appropriately

---

## Work Objectives

### Core Objective
Remediate all 35 issues identified in the codebase audit, prioritizing security and stability fixes first, using TDD methodology to ensure regression safety.

### Concrete Deliverables
- 4 CRITICAL security/stability fixes with tests
- 7 HIGH priority fixes with tests
- 13 MEDIUM priority fixes with tests
- 11 LOW priority improvements with tests
- TUI refactored into modular components
- Test coverage increased from ~40% to ≥70%
- Zero mypy errors in strict mode

### Definition of Done
- [ ] All 35 audit issues resolved with passing tests
- [ ] `uv run pytest tests/ -v` → All tests pass
- [ ] `uv run mypy src/getit/ --ignore-missing-imports` → 0 errors
- [ ] `uv run ruff check src/getit/` → 0 issues
- [ ] No regressions in existing functionality

### Must Have
- Failing test before each fix implementation (TDD RED phase)
- Test passing after fix (TDD GREEN phase)
- Full test suite passing after each CRITICAL/HIGH fix
- Manual verification of TUI functionality after refactoring

### Must NOT Have (Guardrails)
- DO NOT change user-facing behavior unless fixing a bug
- DO NOT refactor code not mentioned in the audit
- DO NOT add new features or "improvements" beyond fixes
- DO NOT skip tests even for "obvious" fixes
- DO NOT proceed to next tier without full test suite passing
- DO NOT touch config files (config.py structure) unless in MEDIUM tier
- DO NOT change TUI keyboard shortcuts or visual layout
- DO NOT add dependencies without explicit approval

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (pytest, 48 tests, conftest.py)
- **User wants tests**: TDD - Tests first
- **Framework**: pytest with uv

### TDD Workflow for Each Fix

Each TODO follows RED-GREEN-REFACTOR:

**Task Structure:**
1. **RED**: Write failing test first
   - Test file: `tests/unit/[module]/test_[feature].py` or `tests/security/test_[issue].py`
   - Test command: `uv run pytest tests/unit/[module]/test_[feature].py -v`
   - Expected: FAIL (test exists, fix doesn't)
2. **GREEN**: Implement minimum code to pass
   - Command: `uv run pytest tests/unit/[module]/test_[feature].py -v`
   - Expected: PASS
3. **REFACTOR**: Clean up while keeping green
   - [x] 2. Fix TOCTOU Race Condition in File Naming

### Test Organization
```
tests/
├── conftest.py              # Existing fixtures
├── security/                # NEW: Security-focused tests
│   ├── __init__.py
│   ├── test_filename_sanitization.py
│   ├── test_toctou_race.py
│   └── test_input_validation.py
├── unit/
│   ├── test_config.py       # Existing
│   ├── core/
│   │   ├── test_downloader.py   # Existing
│   │   ├── test_manager.py      # NEW
│   │   └── test_http_client.py  # NEW
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── test_base.py         # NEW
│   │   ├── test_gofile.py       # NEW
│   │   ├── test_mediafire.py    # NEW
│   │   └── test_onefichier.py   # NEW
│   └── tui/
│       └── __init__.py
└── integration/
    └── __init__.py
```

---

## Task Flow

```
TIER 0: Setup (1)
    ↓
TIER 1: CRITICAL Security/Stability (1-4)
    ↓ [Full test suite must pass before proceeding]
TIER 2: HIGH Priority (5-11)
    ↓ [Full test suite must pass before proceeding]
TIER 3: MEDIUM Priority (12-24)
    ↓
TIER 4: LOW Priority (25-35)
    ↓
Final Verification
```

## Parallelization

| Group | Tasks | Reason |
|-------|-------|--------|
| A | 1, 2 | Independent security fixes |
| B | 3, 4 | Independent retry implementations |
| C | 5, 6, 7 | Independent error handling |
| D | 12, 13, 14 | Independent constant extraction |
| E | 25, 26, 27 | Independent documentation |

| Task | Depends On | Reason |
|------|------------|--------|
| 8 (TUI modals) | 12 (constants) | Uses shared UI constants |
| 9 (TUI widgets) | 8 | Modals must be extracted first |
| 10 (TUI screens) | 9 | Widgets must be extracted first |
| 17 (mypy fixes) | 1-16 | All implementation done first |

---

## TODOs

---

### TIER 0: Setup

- [x] 0. Create Security Test Directory Structure

  **What to do**:
  - Create `tests/security/__init__.py`
  - Create `tests/unit/core/__init__.py` (if not exists)
  - Create `tests/unit/extractors/__init__.py`
  - Create `tests/unit/tui/__init__.py`
  - Verify test discovery: `uv run pytest --collect-only`

  **Must NOT do**:
  - Do not modify existing test files
  - Do not add new dependencies

  **Parallelizable**: NO (first task)

  **References**:
  - `tests/conftest.py:1-100` - Existing fixture patterns
  - `tests/unit/test_config.py:1-50` - Test structure pattern

  **Acceptance Criteria**:
  - [ ] `uv run pytest --collect-only` → Shows new test directories
  - [ ] No errors in test collection

  **Commit**: YES
  - Message: `test: add security and module test directory structure`
  - Files: `tests/security/__init__.py`, `tests/unit/core/__init__.py`, `tests/unit/extractors/__init__.py`, `tests/unit/tui/__init__.py`

---

### TIER 1: CRITICAL Security & Stability (4 issues)

- [x] 1. Add Filename Sanitization to Prevent Directory Traversal

  **What to do**:
  - **RED**: Create `tests/security/test_filename_sanitization.py`
    - Test: `test_sanitize_removes_path_traversal` - Input `"../../.bashrc"` → Output `"__.bashrc"`
    - Test: `test_sanitize_removes_illegal_chars` - Input `"file:name?.txt"` → Output `"file_name_.txt"`
    - Test: `test_sanitize_handles_absolute_paths` - Input `"/etc/passwd"` → Output `"_etc_passwd"`
    - Test: `test_sanitize_truncates_long_names` - Input `"a" * 300` → Output length ≤ 255
    - Test: `test_sanitize_preserves_valid_names` - Input `"valid-file_name.txt"` → Same output
  - **GREEN**: Create `src/getit/utils/sanitize.py` with `sanitize_filename(name: str) -> str`
  - **INTEGRATE**: Update `src/getit/core/manager.py:133` to use sanitization
  - **REFACTOR**: Run full test suite

  **Must NOT do**:
  - Do not change any other manager.py logic
  - Do not add external dependencies (use stdlib re module)

  **Parallelizable**: YES (with task 2)

  **References**:
  - `src/getit/core/manager.py:133` - Current vulnerable line: `output_path = target_dir / file_info.filename`
  - `src/getit/core/manager.py:130-140` - Full context of file path creation
  - `src/getit/extractors/base.py:80-96` - FileInfo dataclass that provides filename
  - OWASP Path Traversal: https://owasp.org/www-community/attacks/Path_Traversal

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/security/test_filename_sanitization.py -v` → 5 FAILED tests
  - [ ] GREEN: `uv run pytest tests/security/test_filename_sanitization.py -v` → 5 PASSED
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass (no regressions)
  - [ ] Manual: Create FileInfo with filename `"../../etc/passwd"`, verify output path is safe

  **Commit**: YES
  - Message: `fix(security): add filename sanitization to prevent directory traversal`
  - Files: `src/getit/utils/sanitize.py`, `src/getit/core/manager.py`, `tests/security/test_filename_sanitization.py`
  - Pre-commit: `uv run pytest tests/ -v`

---

- [x] 2. Fix TOCTOU Race Condition in File Naming

  **What to do**:
  - **RED**: Create `tests/security/test_toctou_race.py`
    - Test: `test_concurrent_same_filename_no_overwrite` - Simulate 10 concurrent tasks with same filename → all get unique paths
    - Test: `test_atomic_file_creation` - File created atomically, no gap between check and create
  - **GREEN**: Update `src/getit/core/manager.py:135-140` to use atomic approach:
    - Replace `while output_path.exists()` loop with atomic file creation using `O_CREAT | O_EXCL` flags
    - Or use `tempfile.mkstemp()` pattern with rename
  - **REFACTOR**: Ensure thread safety for concurrent calls

  **Must NOT do**:
  - Do not change the DownloadTask dataclass
  - Do not introduce locking that could cause deadlocks

  **Parallelizable**: YES (with task 1)

  **References**:
  - `src/getit/core/manager.py:135-140` - Current vulnerable code:
    ```python
    counter = 1
    original_stem = output_path.stem
    original_suffix = output_path.suffix
    while output_path.exists():  # TOCTOU: Check here
        output_path = target_dir / f"{original_stem}_{counter}{original_suffix}"
        counter += 1
    # File could be created by another task between check and actual download
    ```
  - `src/getit/core/manager.py:142-150` - DownloadTask creation that uses the path
  - Python docs: `os.open()` with `O_CREAT | O_EXCL` flags for atomic creation

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/security/test_toctou_race.py -v` → FAILED
  - [ ] GREEN: `uv run pytest tests/security/test_toctou_race.py -v` → PASSED
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Run `getit download` with same URL twice simultaneously → unique filenames

  **Commit**: YES
  - Message: `fix(security): eliminate TOCTOU race condition in file naming`
  - Files: `src/getit/core/manager.py`, `tests/security/test_toctou_race.py`
  - Pre-commit: `uv run pytest tests/ -v`

---

- [x] 3. Implement HTTPClient Retry Logic

  **What to do**:
  - **RED**: Create `tests/unit/core/test_http_client.py`
    - Test: `test_get_retries_on_503` - Mock 503 response, verify 3 retries with backoff
    - Test: `test_get_retries_on_timeout` - Mock timeout, verify retry
    - Test: `test_get_no_retry_on_404` - 404 should fail immediately, no retry
    - Test: `test_get_succeeds_after_retry` - First call fails, second succeeds → returns success
    - Test: `test_max_retries_exhausted` - All retries fail → raises exception
  - **GREEN**: Update `src/getit/utils/http.py`:
    - Add retry decorator or wrapper to `get()`, `post()`, `get_json()`, `get_text()`
    - Implement exponential backoff: `2**attempt` seconds
    - Retry on: 5xx errors, `asyncio.TimeoutError`, `aiohttp.ClientError`
    - Do NOT retry on: 4xx errors (except 429)
  - **REFACTOR**: Extract retry logic into reusable `_with_retry()` method

  **Must NOT do**:
  - Do not change the HTTPClient constructor signature
  - Do not add new dependencies (use existing aiohttp retry capabilities or stdlib)

  **Parallelizable**: YES (with task 4)

  **References**:
  - `src/getit/utils/http.py:20-29` - Constructor with unused `max_retries`:
    ```python
    def __init__(self, ..., max_retries: int = 3):
        self._max_retries = max_retries  # Currently unused!
    ```
  - `src/getit/utils/http.py:74-121` - Methods that need retry logic: `get()`, `post()`, `get_json()`, `get_text()`
  - `src/getit/utils/http.py:30` - Rate limiter that should be respected during retries

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/unit/core/test_http_client.py -v` → 5 FAILED
  - [ ] GREEN: `uv run pytest tests/unit/core/test_http_client.py -v` → 5 PASSED
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Test with unreliable network (throttle) → retries visible in logs

  **Commit**: YES
  - Message: `fix(http): implement retry logic with exponential backoff`
  - Files: `src/getit/utils/http.py`, `tests/unit/core/test_http_client.py`
  - Pre-commit: `uv run pytest tests/ -v`

---

- [x] 4. Add Chunk-Level Retry in FileDownloader

  **What to do**:
  - **RED**: Add tests to `tests/unit/core/test_downloader.py`
    - Test: `test_chunk_timeout_retries` - Single chunk times out, retry succeeds → download completes
    - Test: `test_chunk_max_retries_fails` - All chunk retries fail → task marked FAILED
    - Test: `test_chunk_retry_preserves_progress` - Progress not reset on chunk retry
  - **GREEN**: Update `src/getit/core/downloader.py:201-215`:
    - Wrap `_get_next_chunk()` in retry loop (max 3 attempts per chunk)
    - Add backoff between chunk retries (1s, 2s, 4s)
    - Only fail task after all chunk retries exhausted
  - **REFACTOR**: Extract chunk retry logic into `_get_chunk_with_retry()`

  **Must NOT do**:
  - Do not change the public `download()` method signature
  - Do not add chunk-level retry configuration (use hardcoded 3 retries for now)

  **Parallelizable**: YES (with task 3)

  **References**:
  - `src/getit/core/downloader.py:201-215` - Current code that fails immediately:
    ```python
    async def _get_next_chunk(self, task: DownloadTask, chunk_iter: Any) -> Optional[bytes]:
        try:
            async with asyncio.timeout(self.chunk_timeout):
                return await chunk_iter.__anext__()
        except TimeoutError:
            task.progress.status = DownloadStatus.FAILED  # Immediate failure!
            task.progress.error = f"Chunk download timed out..."
            return None
    ```
  - `src/getit/core/downloader.py:289-341` - `_download_chunks()` that calls `_get_next_chunk()`
  - `tests/unit/core/test_downloader.py` - Existing downloader tests pattern

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/unit/core/test_downloader.py::test_chunk_timeout_retries -v` → FAILED
  - [ ] GREEN: `uv run pytest tests/unit/core/test_downloader.py -v` → All PASSED
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Download large file with throttled connection → completes despite timeouts

  **Commit**: YES
  - Message: `fix(downloader): add chunk-level retry for resilient downloads`
  - Files: `src/getit/core/downloader.py`, `tests/unit/core/test_downloader.py`
  - Pre-commit: `uv run pytest tests/ -v`

---

### 🚨 TIER 1 CHECKPOINT
After completing tasks 1-4:
- [ ] Run full test suite: `uv run pytest tests/ -v` → ALL PASS
- [ ] Run security tests: `uv run pytest tests/security/ -v` → ALL PASS
- [ ] Review diff for unintended changes

---

### TIER 2: HIGH Priority (7 issues)

- [x] 5. Handle Disk Full Error During Download

  **What to do**:
  - **RED**: Add test to `tests/unit/core/test_downloader.py`
    - Test: `test_disk_full_during_write` - Mock `OSError(28, "No space left")` → task fails gracefully with error message
    - Test: `test_disk_full_cleanup` - Partial file cleaned up on disk full error
  - **GREEN**: Update `src/getit/core/downloader.py:322`:
    - Wrap `await file_handle.write(chunk)` in try/except for `OSError`
    - Set `task.progress.status = DownloadStatus.FAILED`
    - Set `task.progress.error = "Disk full: No space left on device"`
    - Clean up partial `.part` file
  - **REFACTOR**: Extract write error handling into `_safe_write_chunk()`

  **Must NOT do**:
  - Do not add disk space pre-check beyond what exists (already at line 264-281)
  - Do not retry on disk full (pointless)

  **Parallelizable**: YES (with tasks 6, 7)

  **References**:
  - `src/getit/core/downloader.py:322` - Current unprotected write: `await file_handle.write(chunk)`
  - `src/getit/core/downloader.py:264-281` - Existing disk space pre-check (doesn't handle mid-download exhaustion)
  - `src/getit/core/downloader.py:405-410` - `_handle_cancellation()` pattern for cleanup

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/unit/core/test_downloader.py::test_disk_full_during_write -v` → FAILED
  - [ ] GREEN: Tests pass
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Fill disk to near-capacity, start download → graceful error message

  **Commit**: YES
  - Message: `fix(downloader): handle disk full error gracefully during download`
  - Files: `src/getit/core/downloader.py`, `tests/unit/core/test_downloader.py`

---

- [ ] 6. Fix 1Fichier Blocking Wait with Timeout/Callback

  **What to do**:
  - **RED**: Create `tests/unit/extractors/test_onefichier.py`
    - Test: `test_wait_time_honored` - 5 second wait → extraction completes after wait
    - Test: `test_long_wait_raises_error` - 300+ second wait → raises ExtractorError immediately
    - Test: `test_wait_does_not_block_other_tasks` - Multiple concurrent extractions → all proceed
  - **GREEN**: Update `src/getit/extractors/onefichier.py:134-135`:
    - Cap maximum wait at 60 seconds
    - For waits > 60s, raise `ExtractorError("Wait time too long, try again later")`
    - Add logging for wait time: `logger.info(f"Waiting {wait_time}s as required by 1Fichier")`
  - **REFACTOR**: Extract wait logic into `_handle_rate_limit(wait_time: int)`

  **Must NOT do**:
  - Do not remove the wait functionality (it's required by 1Fichier)
  - Do not add threading (stay async)

  **Parallelizable**: YES (with tasks 5, 7)

  **References**:
  - `src/getit/extractors/onefichier.py:134-135` - Current blocking wait:
    ```python
    if 0 < wait_time < 300:
        await asyncio.sleep(wait_time + 1)  # Can block for 5 minutes!
    ```
  - `src/getit/extractors/onefichier.py:129-133` - Wait time parsing logic
  - `src/getit/extractors/base.py:13-32` - ExtractorError class hierarchy

  **Acceptance Criteria**:
  - [ ] RED: `uv run pytest tests/unit/extractors/test_onefichier.py -v` → FAILED
  - [ ] GREEN: Tests pass
  - [ ] Wait times > 60s raise error immediately
  - [ ] Wait times ≤ 60s complete normally

  **Commit**: YES
  - Message: `fix(extractor): cap 1Fichier wait time to prevent long blocks`
  - Files: `src/getit/extractors/onefichier.py`, `tests/unit/extractors/test_onefichier.py`

---

- [ ] 7. Add Concurrent Folder Extraction

  **What to do**:
  - **RED**: Create `tests/unit/extractors/test_gofile.py`
    - Test: `test_folder_extraction_concurrent` - Folder with 10 files → extracted in parallel, not sequentially
    - Test: `test_folder_extraction_respects_rate_limit` - Concurrency limited to rate limiter
  - **GREEN**: Update folder extraction in:
    - `src/getit/extractors/gofile.py:208-218` - Use `asyncio.gather()` with semaphore
    - `src/getit/extractors/mega.py:247-273` - Use `asyncio.gather()` with semaphore
    - `src/getit/extractors/mediafire.py:170-175` - Use `asyncio.gather()` with semaphore
  - **REFACTOR**: Create helper in `BaseExtractor` for concurrent extraction pattern

  **Must NOT do**:
  - Do not remove rate limiting (keep existing `AsyncLimiter`)
  - Do not parallelize beyond 5 concurrent subfolder extractions

  **Parallelizable**: NO (depends on extractor structure understanding)

  **References**:
  - `src/getit/extractors/gofile.py:208-218` - Sequential folder extraction:
    ```python
    for item in children:
        if item.get("type") == "folder" and current_depth < max_depth:
            sub_files = await self._extract_recursive(...)  # Sequential!
            files.extend(sub_files)
    ```
  - `src/getit/extractors/mega.py:247-273` - Similar sequential pattern
  - `src/getit/extractors/gofile.py:61` - Existing rate limiter to respect

  **Acceptance Criteria**:
  - [ ] RED: Tests fail (sequential behavior)
  - [ ] GREEN: Tests pass (concurrent behavior)
  - [ ] FULL: `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Extract folder with 20+ files → visibly faster

  **Commit**: YES
  - Message: `perf(extractors): add concurrent folder extraction`
  - Files: `src/getit/extractors/gofile.py`, `src/getit/extractors/mega.py`, `src/getit/extractors/mediafire.py`, `tests/unit/extractors/test_gofile.py`

---

- [ ] 8. TUI Refactor Phase 1: Extract Modal Screens

  **What to do**:
  - **RED**: Create `tests/unit/tui/test_modals.py`
    - Test: `test_add_url_screen_returns_url` - Modal returns (url, password) tuple
    - Test: `test_batch_file_screen_validates_path` - Invalid path → None returned
    - Test: `test_settings_screen_saves_config` - Save button → config updated
  - **GREEN**: Extract from `src/getit/tui/app.py` to new files:
    - Create `src/getit/tui/screens/__init__.py`
    - Create `src/getit/tui/screens/add_url.py` ← Move `AddUrlScreen` (lines 257-324)
    - Create `src/getit/tui/screens/batch_import.py` ← Move `BatchFileScreen` (lines 139-255)
    - Create `src/getit/tui/screens/error_details.py` ← Move `ErrorDetailsScreen` (lines 326-390)
    - Create `src/getit/tui/screens/settings.py` ← Move `SettingsScreen` (lines 392-498)
  - **REFACTOR**: Update imports in `app.py` to use new modules

  **Must NOT do**:
  - Do not change modal behavior or appearance
  - Do not change keyboard shortcuts
  - Do not add new features to modals

  **Parallelizable**: NO (large refactor, serialize)

  **References**:
  - `src/getit/tui/app.py:139-255` - BatchFileScreen class
  - `src/getit/tui/app.py:257-324` - AddUrlScreen class
  - `src/getit/tui/app.py:326-390` - ErrorDetailsScreen class
  - `src/getit/tui/app.py:392-498` - SettingsScreen class
  - `src/getit/tui/app.py:84-112` - `MODAL_BASE_CSS` shared by modals

  **Acceptance Criteria**:
  - [ ] `app.py` reduced by ~400 lines (from 1021 to ~620)
  - [ ] All modals work identically in TUI
  - [ ] `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Open each modal in TUI → same appearance and behavior

  **Commit**: YES
  - Message: `refactor(tui): extract modal screens to separate modules`
  - Files: `src/getit/tui/screens/*.py`, `src/getit/tui/app.py`

---

- [ ] 9. TUI Refactor Phase 2: Extract Widgets

  **What to do**:
  - **RED**: Create `tests/unit/tui/test_widgets.py`
    - Test: `test_status_bar_updates` - `update_status()` changes displayed values
    - Test: `test_status_bar_formatting` - Speed formatted correctly
  - **GREEN**: Extract from `src/getit/tui/app.py` to new files:
    - Create `src/getit/tui/widgets/__init__.py`
    - Create `src/getit/tui/widgets/status_bar.py` ← Move `StatusBar` (lines 500-537)
    - Create `src/getit/tui/widgets/formatters.py` ← Move `format_size`, `format_speed`, `format_eta` (lines 115-136)
  - **REFACTOR**: Update imports in `app.py`

  **Must NOT do**:
  - Do not change StatusBar appearance
  - Do not add new formatting options

  **Parallelizable**: NO (depends on task 8)

  **References**:
  - `src/getit/tui/app.py:500-537` - StatusBar class
  - `src/getit/tui/app.py:115-136` - Formatter functions
  - `src/getit/tui/app.py:79-82` - Unicode constants used by formatters

  **Acceptance Criteria**:
  - [ ] `app.py` reduced to ~500 lines
  - [ ] StatusBar displays correctly
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `refactor(tui): extract widgets to separate modules`
  - Files: `src/getit/tui/widgets/*.py`, `src/getit/tui/app.py`

---

- [ ] 10. TUI Refactor Phase 3: Clean Up Main App

  **What to do**:
  - **GREEN**: Final cleanup of `src/getit/tui/app.py`:
    - Remove redundant imports
    - Organize remaining code into logical sections with comments
    - Ensure all extracted modules are properly imported
  - **REFACTOR**: Run linting and formatting:
    - `uv run ruff check src/getit/tui/ --fix`
    - `uv run ruff format src/getit/tui/`

  **Must NOT do**:
  - Do not extract more code (scope locked)
  - Do not add new functionality

  **Parallelizable**: NO (depends on tasks 8, 9)

  **References**:
  - `src/getit/tui/app.py` - Remaining app code after extractions
  - `src/getit/tui/screens/__init__.py` - Screen imports
  - `src/getit/tui/widgets/__init__.py` - Widget imports

  **Acceptance Criteria**:
  - [ ] `app.py` is ~450-500 lines (down from 1021)
  - [ ] `uv run ruff check src/getit/tui/` → 0 issues
  - [ ] `uv run pytest tests/ -v` → All tests pass
  - [ ] Manual: Full TUI workflow test → all features work

  **Commit**: YES
  - Message: `refactor(tui): finalize modular structure`
  - Files: `src/getit/tui/app.py`

---

- [ ] 11. Replace Silent Exception Patterns with Proper Error Handling

  **What to do**:
  - **RED**: Add tests for error propagation in extractors
    - Test: `test_mediafire_api_error_propagates` - API error → ExtractorError raised
    - Test: `test_mega_key_error_propagates` - Invalid key → clear error message
  - **GREEN**: Replace `except Exception: pass` patterns with proper handling:
    - `src/getit/extractors/mediafire.py:60-61` → Log and raise ExtractorError
    - `src/getit/extractors/mediafire.py:95-96` → Log and return None with reason
    - `src/getit/extractors/mediafire.py:124-125` → Log and break with warning
    - `src/getit/extractors/mega.py:203-204` → Log and continue with warning
    - `src/getit/extractors/mega.py:272-273` → Log and continue with warning
  - **REFACTOR**: Add logging import where missing

  **Must NOT do**:
  - Do not change the success path behavior
  - Do not add overly verbose logging

  **Parallelizable**: YES (after TIER 1 complete)

  **References**:
  - `src/getit/extractors/mediafire.py:60-61`:
    ```python
    except Exception:
        pass  # Silent failure - should log and handle
    ```
  - Similar patterns in `mega.py:203-204`, `mega.py:272-273`

  **Acceptance Criteria**:
  - [ ] No `except Exception: pass` patterns remain in extractors
  - [ ] Errors are logged with context
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `fix(extractors): replace silent exception handling with proper errors`
  - Files: `src/getit/extractors/mediafire.py`, `src/getit/extractors/mega.py`

---

### 🚨 TIER 2 CHECKPOINT
After completing tasks 5-11:
- [ ] Run full test suite: `uv run pytest tests/ -v` → ALL PASS
- [ ] Manual TUI verification: All features work
- [ ] Review TUI file sizes: `wc -l src/getit/tui/*.py src/getit/tui/**/*.py`

---

### TIER 3: MEDIUM Priority (13 issues)

- [ ] 12. Extract Magic Numbers to Constants Module

  **What to do**:
  - Create `src/getit/constants.py` with:
    - `DEFAULT_CHUNK_SIZE = 1024 * 1024`
    - `EMA_SMOOTHING_ALPHA = 0.3`
    - `DEFAULT_USER_AGENT = "Mozilla/5.0..."`
    - `TOKEN_TTL_SECONDS = 86400`
    - `GOFILE_FALLBACK_WT = "4fd6sg89d7s6"`
  - Update references in:
    - `src/getit/core/downloader.py:106`
    - `src/getit/core/downloader.py:227`
    - `src/getit/utils/http.py:33-34`
    - `src/getit/extractors/gofile.py:43-44`

  **Parallelizable**: YES (with tasks 13, 14)

  **References**:
  - `src/getit/core/downloader.py:106` - `chunk_size: int = 1024 * 1024`
  - `src/getit/core/downloader.py:227` - `alpha = 0.3`
  - `src/getit/utils/http.py:33-34` - Hardcoded User-Agent

  **Acceptance Criteria**:
  - [ ] No magic numbers in source files
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `refactor: extract magic numbers to constants module`

---

- [ ] 13. Add URL Validation in TUI Before Accepting

  **What to do**:
  - **RED**: Create `tests/unit/tui/test_validation.py`
    - Test: `test_invalid_url_rejected` - "not-a-url" → error shown, modal stays open
    - Test: `test_valid_url_accepted` - "https://gofile.io/d/abc" → modal dismisses
  - **GREEN**: Update `src/getit/tui/screens/add_url.py` (after extraction):
    - Add URL validation using `urllib.parse.urlparse()`
    - Show error notification for invalid URLs
    - Keep modal open until valid URL entered
  - **REFACTOR**: Create shared `validate_url()` helper

  **Parallelizable**: YES (with tasks 12, 14)

  **References**:
  - `src/getit/tui/app.py:310-319` - Current `on_add()` with no validation
  - `src/getit/extractors/base.py:71-76` - `validate_url_scheme()` function to reuse

  **Acceptance Criteria**:
  - [ ] Invalid URLs show error, modal stays open
  - [ ] Valid URLs proceed normally
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `feat(tui): add URL validation before accepting input`

---

- [ ] 14. Fix Fragile Fallback ID Extraction

  **What to do**:
  - **RED**: Create `tests/unit/extractors/test_base.py`
    - Test: `test_extract_id_with_query_params` - "https://host.com/file?dl=1" → "file"
    - Test: `test_extract_id_with_trailing_slash` - "https://host.com/file/" → "file"
    - Test: `test_extract_id_empty_path` - "https://host.com/" → None
  - **GREEN**: Update `src/getit/extractors/base.py:135-137`:
    - Strip query parameters before extracting
    - Handle trailing slashes
    - Return None for truly empty paths

  **Parallelizable**: YES (with tasks 12, 13)

  **References**:
  - `src/getit/extractors/base.py:135-137`:
    ```python
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    return parts[-1] if parts else None  # Fragile!
    ```

  **Acceptance Criteria**:
  - [ ] Query params don't affect ID extraction
  - [ ] Trailing slashes handled correctly
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `fix(extractors): robust fallback ID extraction`

---

- [ ] 15. Create Folder Extraction Mixin for Code Deduplication

  **What to do**:
  - Create `src/getit/extractors/mixins.py` with `FolderExtractionMixin`:
    - Common `extract_folder()` boilerplate
    - Abstract `_get_folder_contents()` method
  - Update `gofile.py`, `mediafire.py`, `pixeldrain.py` to use mixin

  **Parallelizable**: NO (depends on task 7)

  **References**:
  - `src/getit/extractors/gofile.py:222-246` - Folder extraction pattern
  - `src/getit/extractors/mediafire.py:178-190` - Similar pattern
  - `src/getit/extractors/pixeldrain.py` - Similar pattern

  **Acceptance Criteria**:
  - [ ] Duplicate code eliminated
  - [ ] All folder extraction works identically
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES
  - Message: `refactor(extractors): deduplicate folder extraction with mixin`

---

- [ ] 16. Add Type Annotations for Any Escapes

  **What to do**:
  - Fix `Any` type annotations:
    - `src/getit/core/downloader.py:139` - `decryptor: Optional[AES.CtrMode]`
    - `src/getit/core/downloader.py:292` - `response: aiohttp.ClientResponse`
    - `src/getit/core/downloader.py:293` - `file_handle: aiofiles.threadpool.binary.AsyncBufferedIOBase`
  - Add missing type parameters:
    - `deque[float]` instead of `deque`
    - `dict[str, Any]` where appropriate

  **Parallelizable**: YES

  **References**:
  - `src/getit/core/downloader.py:53` - `_speed_samples: deque` → `deque[float]`
  - `AUDIT_REPORT.md:77-83` - List of type issues

  **Acceptance Criteria**:
  - [ ] `uv run mypy src/getit/core/downloader.py --ignore-missing-imports` → 0 errors

  **Commit**: YES
  - Message: `fix(types): add missing type annotations in downloader`

---

- [ ] 17. Fix All Mypy Errors (64 total)

  **What to do**:
  - Run `uv run mypy src/getit/ --ignore-missing-imports` to get current errors
  - Fix errors by file:
    - `tui/app.py` (18 errors) - Add missing annotations
    - `extractors/onefichier.py` (6 errors) - Fix BeautifulSoup types
    - `extractors/mediafire.py` (5 errors) - Fix BeautifulSoup types
    - `config.py` (6 errors) - Add missing annotations
    - Remaining files (29 errors)

  **Parallelizable**: YES (by file)

  **References**:
  - `AUDIT_REPORT.md:58-83` - Full mypy error breakdown
  - Each file's current type annotations

  **Acceptance Criteria**:
  - [ ] `uv run mypy src/getit/ --ignore-missing-imports` → 0 errors
  - [ ] `uv run pytest tests/ -v` → All tests pass

  **Commit**: YES (one commit per file or grouped)
  - Message: `fix(types): resolve mypy errors in [module]`

---

- [ ] 18-24. Additional MEDIUM Priority Fixes

  **Tasks 18-24** cover:
  - 18: Add logging to extractors (replace prints with structured logging)
  - 19: Validate config on load (catch invalid values early)
  - 20: Add connection pool limits documentation
  - 21: Improve extractor docstrings
  - 22: Add module-level docstrings
  - 23: Standardize error messages
  - 24: Add type stubs for external dependencies (if needed)

  Each follows same TDD pattern. See references in source files.

  **Acceptance Criteria**:
  - [ ] `uv run pytest tests/ -v` → All tests pass
  - [ ] `uv run ruff check src/getit/` → 0 issues

---

### TIER 4: LOW Priority (11 issues)

- [ ] 25-35. LOW Priority Improvements

  **Tasks 25-35** cover:
  - 25-27: Documentation improvements (README, CONTRIBUTING, API docs)
  - 28-30: Test coverage improvements (manager, CLI, history)
  - 31-33: Naming consistency fixes (use `lsp_rename`)
  - 34: Code style cleanup (run ruff format)
  - 35: Remove any remaining commented code

  Each follows same pattern. Use `lsp_rename` for all symbol renames.

  **Acceptance Criteria**:
  - [ ] `uv run pytest tests/ --cov=src/getit` → Coverage ≥ 70%
  - [ ] All tests pass

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 0 | `test: add test directory structure` | tests/**/__init__.py | pytest --collect-only |
| 1 | `fix(security): add filename sanitization` | manager.py, sanitize.py, tests | pytest tests/ |
| 2 | `fix(security): fix TOCTOU race condition` | manager.py, tests | pytest tests/ |
| 3 | `fix(http): implement retry logic` | http.py, tests | pytest tests/ |
| 4 | `fix(downloader): add chunk-level retry` | downloader.py, tests | pytest tests/ |
| 5 | `fix(downloader): handle disk full error` | downloader.py, tests | pytest tests/ |
| 6 | `fix(extractor): cap 1Fichier wait time` | onefichier.py, tests | pytest tests/ |
| 7 | `perf(extractors): concurrent folder extraction` | extractors/*.py, tests | pytest tests/ |
| 8 | `refactor(tui): extract modal screens` | tui/screens/*.py, app.py | pytest tests/ |
| 9 | `refactor(tui): extract widgets` | tui/widgets/*.py, app.py | pytest tests/ |
| 10 | `refactor(tui): finalize structure` | tui/app.py | pytest tests/ |
| 11 | `fix(extractors): proper error handling` | extractors/*.py | pytest tests/ |
| 12-17 | `refactor: [specific improvement]` | varies | pytest tests/ |
| 18-35 | `chore: [specific improvement]` | varies | pytest tests/ |

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
uv run pytest tests/ -v

# Coverage target met
uv run pytest tests/ --cov=src/getit --cov-report=term-missing

# No mypy errors
uv run mypy src/getit/ --ignore-missing-imports

# No linting issues
uv run ruff check src/getit/

# TUI still works (manual)
uv run python -m getit tui
```

### Final Checklist
- [ ] All 35 audit issues addressed with tests
- [ ] Test coverage ≥ 70% (up from ~40%)
- [ ] Zero mypy errors
- [ ] Zero ruff errors
- [ ] TUI fully functional (manual verification)
- [ ] No regressions in existing features
- [ ] All commits follow conventional commit format
