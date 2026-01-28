# Known Typing Exceptions

This document explains the `# type: ignore` comments used in the codebase and why they're necessary.

## Textual Framework Limitations

The Textual TUI framework has incomplete type stubs, causing false positives with strict mypy.

### DataTable Column Keys (`tui/app.py`)

```python
table.update_cell(row, col, value)  # type: ignore[arg-type]
```

**Reason:** `DataTable.update_cell()` expects `ColumnKey | str` for the column parameter, but our column key dict returns `object` type. The runtime behavior is correct.

### Reactive Properties (`tui/app.py`)

```python
self.dark = not self.dark  # type: ignore[has-type]
```

**Reason:** Textual's `dark` is a reactive property defined on the App class. Mypy cannot determine its type at static analysis time, but it's a boolean at runtime.

### Worker Decorator (`tui/app.py`)

```python
await self._add_download(...)  # type: ignore[misc]
```

**Reason:** Textual's `@work` decorator transforms async methods. The return type becomes `Worker[T]` which mypy doesn't recognize as properly awaitable, though it is at runtime.

## aiohttp/Third-Party Library Quirks

### Dict Update Type Mismatch (`extractors/mega.py`)

```python
params.update(query_params)  # type: ignore[arg-type]
```

**Reason:** When `params` is `dict[str, int]` and `query_params` is `dict[str, str]`, mypy complains about incompatible types. In practice, the resulting `dict[str, int | str]` works correctly with aiohttp's parameter handling.

## BeautifulSoup Type Handling

BeautifulSoup's `.get()` method returns `str | list[str] | None` (called `AttributeValueList` internally). We handle this by:

1. Explicit `str()` casts when we know the value is a string
2. Checking for `None` before use
3. Using `if value:` guards

Example pattern:
```python
href = tag.get("href")
if href:
    url = str(href)  # Cast handles AttributeValueList case
```

## Configuration

Our `pyproject.toml` mypy config is intentionally relaxed from `strict = true`:

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = false
disallow_untyped_defs = false
check_untyped_defs = true
no_implicit_optional = true
strict_equality = true
ignore_missing_imports = true
```

This keeps useful checks while avoiding false positives from third-party libraries with incomplete stubs.

## Adding New Type Ignores

When adding a new `# type: ignore`, always:

1. Use the specific error code: `# type: ignore[error-code]`
2. Add a brief explanation: `# type: ignore[arg-type]  # Textual stubs incomplete`
3. Document in this file if it's a recurring pattern
