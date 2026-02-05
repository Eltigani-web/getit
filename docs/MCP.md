# MCP Server Guide

This document describes the Model Context Protocol (MCP) server provided by GetIt. It covers
quick start instructions, available tools/resources/prompts, and client configuration examples.

## Overview

GetIt ships with an MCP server that exposes the same download capabilities as the CLI/TUI. The
server is implemented with FastMCP and runs over the stdio transport, making it compatible with
popular MCP clients (Claude Desktop, Cursor, Windsurf) and any generic MCP client.

## Quick Start

1. Install GetIt with MCP dependencies:
   ```bash
   pip install getit-cli
   ```

2. Start the MCP server:
   ```bash
   getit-mcp
   # or
   python -m getit.mcp.server
   ```

3. Configure your client using one of the examples in
   [`examples/mcp-configs/`](../examples/mcp-configs/).

## Available Tools

### `download(url, output_dir, password)`
Start a download task for a file or folder.

**Parameters**
- `url` (string, required): File or folder URL.
- `output_dir` (string, optional): Destination directory. Defaults to `./downloads`.
- `password` (string, optional): Password for protected content.

**Returns**
```json
{ "task_id": "<id>" }
```

### `list_files(url, password)`
Inspect a URL without downloading.

**Parameters**
- `url` (string, required)
- `password` (string, optional)

**Returns**
```json
{
  "files": [
    {
      "url": "https://...",
      "filename": "example.txt",
      "size": 12345,
      "direct_url": "https://...",
      "password_protected": false,
      "checksum": "...",
      "checksum_type": "md5",
      "parent_folder": null,
      "extractor_name": "gofile",
      "encrypted": false
    }
  ]
}
```

### `get_download_status(task_id)`
Retrieve status and progress for a task.

**Parameters**
- `task_id` (string, required)

**Returns**
```json
{
  "task_id": "<id>",
  "url": "https://...",
  "status": "downloading",
  "progress": { "percentage": 50.0, "downloaded": 512.0, "total": 1024.0 },
  "output_dir": "/path/to/downloads",
  "created_at": "2024-01-01T12:00:00",
  "updated_at": "2024-01-01T12:30:00",
  "error": null
}
```

### `cancel_download(task_id)`
Cancel a running download task.

**Parameters**
- `task_id` (string, required)

**Returns**
```json
{ "success": true }
```

## Available Resources

### `active-downloads://list`
Returns a live list of active download tasks. Subscribing clients receive updates when progress,
completion, or errors occur.

## Available Prompts

### `download_workflow`
Guided prompt that walks an agent through URL input, provider detection, password handling, and
output directory selection.

## Client Configuration Examples

All configurations below are also available as JSON files in
[`examples/mcp-configs/`](../examples/mcp-configs/).

### Claude Desktop
```json
{
  "mcpServers": {
    "getit": {
      "command": "getit-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

### Cursor
```json
{
  "mcpServers": {
    "getit": {
      "command": "getit-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

### Windsurf
```json
{
  "mcpServers": {
    "getit": {
      "command": "getit-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

### Generic stdio client
```json
{
  "name": "getit",
  "transport": "stdio",
  "command": "getit-mcp",
  "args": [],
  "env": {}
}
```

## Troubleshooting

- **Server fails to start**: ensure `getit-cli` is installed and `getit-mcp` is on PATH.
- **Tools missing**: confirm the server is started from the repo root or installed package.
- **No download progress**: verify the URL is supported and reachable.

## Related Docs

- [MCP testing guide](mcp-testing.md)
- [Architecture overview](ARCHITECTURE.md)
