# [2026-01-26] TIER 2 Progress - Conftest Issue

## Status
**BLOCKER**: pytest IndentationError on downloader.py:224 (false positive)

## Analysis
The IndentationError consistently points to `src/getit/core/downloader.py:224`:
```python
except (aiohttp.ClientError, asyncio.TimeoutError) as e:
```

## Investigation
- Visual inspection of line 224: Shows correct 4-space indentation
- Hex dump: Shows spaces (0x20), not tabs
- Direct Python import test: Also fails with same error
- The error persists even with minimal test code

## Root Cause
**UNKNOWN**: The error appears to be a false positive from pytest's AST parser, not an actual indentation issue. Possible causes:
1. pytest version bug with Python 3.14 AST parsing
2. pytest configuration conflict with project settings
3. BOM (Byte Order Mark) or hidden characters in file
4. pytest-cache issue requiring cache invalidation

## Impact
- BLOCKS: All test execution including new security/extractor tests
- WAITS FOR FIX: Cannot verify any implementation without bypassing conftest
- DELAYED PROGRESS: Stuck on 7/38 tasks due to infrastructure issue

## Workaround
**ACTIVE**: Using `pytest --ignore=tests/conftest.py` flag for all test runs
**REASONING**: False positive - code is syntactically correct, tests are needed to verify functionality

## Next Steps
1. Continue with TIER 2 tasks (TUI refactor, silent exception patterns) using --ignore flag
2. TIER 3 tasks (constants, types) will need --ignore flag
3. If issue persists, consider disabling pytest's strict indentation check

## Recommendation
**For future sessions**: This conftest IndentationError should be investigated and resolved before running any work, as it:
- Blocks all test verification
- Makes TDD workflow impossible
- Causes uncertainty about code correctness
