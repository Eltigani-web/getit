# MCP Testing Guide

This guide provides executable MCP server testing scenarios for agents and a manual QA checklist
for humans. All scenarios avoid real downloads by relying on the existing MCP test suite or
synthetic inputs.

## Agent-Executable Scenarios

> Run these commands from the repository root.

### Scenario 1: MCP unit tests (tools/resources/prompts/server)
**Command:**
```bash
pytest tests/unit/mcp/ -v --tb=short
```
**Expected:** All unit tests pass.

### Scenario 2: MCP end-to-end tests
**Command:**
```bash
pytest tests/integration/test_mcp_e2e.py -v --tb=short
```
**Expected:** All integration tests pass.

### Scenario 3: MCP server creates successfully
**Command:**
```bash
python3 -c "from getit.mcp.server import create_server; create_server(); print('OK')"
```
**Expected:** Prints `OK` with no exceptions.

### Scenario 4: Tools are registered
**Command:**
```bash
python3 - <<'PY'
import asyncio
from getit.mcp.server import mcp

async def main():
    tools = await mcp.list_tools()
    print([t.name for t in tools])

asyncio.run(main())
PY
```
**Expected:** Output includes `download`, `list_files`, `get_download_status`, `cancel_download`.

### Scenario 5: Resources are registered
**Command:**
```bash
python3 - <<'PY'
import asyncio
from getit.mcp.server import mcp

async def main():
    resources = await mcp.list_resources()
    print([str(r.uri) for r in resources])

asyncio.run(main())
PY
```
**Expected:** Output includes `active-downloads://list`.

### Scenario 6: Prompt is registered
**Command:**
```bash
python3 - <<'PY'
import asyncio
from getit.mcp.server import mcp

async def main():
    prompts = await mcp.list_prompts()
    print([p.name for p in prompts])

asyncio.run(main())
PY
```
**Expected:** Output includes `download_workflow`.

### Scenario 7: Prompt retrieval returns content
**Command:**
```bash
python3 - <<'PY'
import asyncio
from getit.mcp.server import mcp

async def main():
    prompt = await mcp.get_prompt("download_workflow")
    print(len(prompt.messages))

asyncio.run(main())
PY
```
**Expected:** Prints a positive integer (number of messages).

## Human QA Checklist

Use this checklist for manual verification when releasing or after significant MCP changes.

- [ ] **Server startup**: `getit-mcp` runs without errors and stays active until terminated.
- [ ] **Tool discovery**: Client can list tools and sees the four tools documented.
- [ ] **Tool invocation**: Calling `download` returns a `task_id` (use tests for no-network runs).
- [ ] **Status checks**: `get_download_status` reports a valid status for a known task.
- [ ] **Cancellation**: `cancel_download` returns `success: true` for a known active task.
- [ ] **Resource updates**: `active-downloads://list` is accessible and updates on progress events.
- [ ] **Prompt availability**: `download_workflow` prompt is returned by client.
- [ ] **Docs alignment**: README and `docs/MCP.md` reflect actual tool names and parameters.

## Notes

- The automated test suite uses a `FakeDownloadService` to avoid network activity.
- If running in a clean environment, install dev dependencies: `pip install -e ".[dev]"`.
