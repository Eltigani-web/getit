# Architecture Overview

GetIt is organized as a layered, event-driven system that exposes the same
download capabilities through CLI, TUI, and MCP server interfaces.

## High-Level Diagram

```
          ┌───────────────────────┐
          │        CLI / TUI       │
          └──────────┬────────────┘
                     │
                     │
          ┌──────────▼────────────┐
          │    DownloadService    │
          │  (service.py facade)  │
          └──────────┬────────────┘
                     │
         ┌───────────┼──────────────┐
         │           │              │
         ▼           ▼              ▼
  TaskRegistry   EventBus     DownloadManager
   (tasks.py)   (events.py)    (core/manager.py)
         │           │              │
         │           │              ▼
         │           │        FileDownloader
         │           │        (core/downloader.py)
         │           │              │
         │           └───────┐      ▼
         │                   │  Extractors
         │                   │ (extractors/*)
         ▼                   │
     SQLite DB               │
                             ▼
                         HTTPClient

          ┌────────────────────────────────┐
          │           MCP Server           │
          │ (mcp/tools, resources, prompts)│
          └───────────┬────────────────────┘
                      │
                      ▼
              DownloadService
```

## Core Components

### 1. Extractor Registry (`registry.py`)
- Provides `ExtractorRegistry.register` for self-registration.
- Routes URLs to extractors via `ExtractorRegistry.get_for_url()`.
- Extractors are loaded by importing `getit.extractors`.

### 2. Download Service (`service.py`)
- Thin facade coordinating:
  - `DownloadManager` for the actual download flow
  - `TaskRegistry` for persistence and status
  - `EventBus` for progress streaming
- Ensures the same API works for CLI, TUI, and MCP.

### 3. Task Registry (`tasks.py`)
- SQLite-backed persistence for active download tasks.
- Stores task metadata and progress as JSON.
- Used by MCP tools (status, cancel) and future history views.

### 4. Event Bus (`events.py`)
- Simple publish/subscribe for progress updates.
- Events:
  - `download_progress`
  - `download_complete`
  - `download_error`
- Used by CLI progress bars and MCP resource updates.

### 5. Download Manager (`core/manager.py`)
- Orchestrates extraction, task creation, and concurrent downloads.
- Instantiates extractors from the registry.
- Delegates IO to `FileDownloader`.

### 6. File Downloader (`core/downloader.py`)
- Handles resumable downloads, encryption, checksum validation.
- Emits progress via callbacks that bubble up to the service.

## MCP Server (`mcp/*`)

The MCP server exposes download capabilities to agent systems.

**Tools:**
- `download(url, output_dir, password)`
- `list_files(url, password)`
- `get_download_status(task_id)`
- `cancel_download(task_id)`

**Resource:**
- `active-downloads://list` (live updates)

**Prompt:**
- `download_workflow`

All MCP interactions go through `DownloadService`, preserving business logic
consistency across interfaces.

## Extension Points

1. **New Providers**
   - Implement a new extractor in `extractors/` and add
     `@ExtractorRegistry.register`.

2. **New Interfaces**
   - Integrate additional frontends by using `DownloadService` and `EventBus`.

3. **Additional MCP Resources**
   - New resources can subscribe to `EventBus` for live updates.

## Data Flow (Download)

1. CLI/TUI/MCP calls `DownloadService.download()`
2. Service records task in `TaskRegistry`
3. `DownloadManager` extracts files and starts download tasks
4. `FileDownloader` streams data and emits progress callbacks
5. `EventBus` broadcasts progress to UI and MCP subscribers
6. Task state persists in SQLite
