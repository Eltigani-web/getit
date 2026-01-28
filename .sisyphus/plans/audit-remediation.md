# Audit Remediation Work Plan

## Context
### Original Request
Create a comprehensive work plan to address ALL issues identified in codebase audit of `getit` TUI file downloader. The audit identified 35 issues across 4 severity levels.

### Interview Summary
**Key Discussions**:
- **Priority**: Security First approach - CRITICAL → HIGH → MEDIUM → LOW
- **Testing**: TDD - Write failing tests before implementing fixes
- **TUI Refactoring**: Phased approach - modals → widgets → screens (incremental extraction)

### Research Findings
- Existing test infrastructure: pytest with 48 tests in `tests/`, 15 fixtures in `conftest.py`
- Test command: `uv run pytest tests/ -v`
- Coverage command: `uv run pytest tests/ --cov=src/getit --cov-report=html`
- Current coverage: ~60% on downloader, ~90% on config, 0% on extractors/manager/TUI
- Uses: aiohttp, Textual, Pydantic, aiofiles, pycryptodomex, BeautifulSoup
- Project structure: `src/getit/` with core/, extractors/, tui/, utils/, storage/

### Metis Review
**Identified Gaps** (addressed):
- Audit location: Comprehensive audit performed during this session (files analyzed in detail)
- TOCTOU location: `manager.py:138-140` (file existence check race)
- TUI boundaries: `app.py` only (1021 lines), extract to `tui/screens/` and `tui/widgets/`
- 1Fichier blocking: Code-fixable via `asyncio.wait_for()` with timeout/callback pattern
- Dependencies: Most issues are independent; analyzed and sequenced appropriately

### Dependencies
Task 0 completed: Test directory structure created
Tasks 1-4 complete: Security fixes implemented with tests
Tasks 5-7 complete: HIGH priority fixes with tests
Tasks 8-20 complete: MEDIUM priority fixes with tests
Tasks 21-33 complete: LOW priority improvements with tests

### Work Objectives
Remediate all 35 issues identified in codebase audit, prioritizing security and stability fixes first, using TDD methodology to ensure regression safety.

### Concrete Deliverables
- 4 CRITICAL security/stability fixes with tests
- 7 HIGH priority fixes with tests
- 13 MEDIUM priority fixes with tests
- 11 LOW priority improvements with tests

### Definition of Done
- [x] All 35 audit issues resolved with passing tests
- [x] `uv run pytest tests/ -v` → All tests pass
- [x] `uv run mypy src/getit/ --ignore-missing-imports` → 0 errors
- [x] `uv run ruff check src/getit/` → 0 issues
- [x] No regressions in existing functionality
- [x] Test coverage ≥ 70% (up from ~40%)

### Must Have
- Failing test before each fix implementation (TDD RED phase)
- Test passing after fix implementation (TDD GREEN phase)
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
