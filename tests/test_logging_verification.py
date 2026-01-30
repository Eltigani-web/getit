#!/usr/bin/env python3
"""Verification test script for structured logging.

Tests:
1. JSON format output with run_id
2. Plain format output
3. Secret redaction
4. NO_COLOR flag disables ANSI
5. Non-TTY output (piped) uses JSON
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from time import sleep


def test_json_format_with_run_id() -> None:
    """Test JSON format output includes run_id."""
    env = os.environ.copy()
    env["LOG_FORMAT"] = "json"
    env["LOG_LEVEL"] = "INFO"

    script_dir = Path(__file__).parent.parent / "src"
    script = f"""
import sys
import os
from time import sleep
sys.path.insert(0, '{script_dir}')
from getit.utils.logging import setup_logging, get_logger, set_run_id, set_download_id, shutdown_logging

setup_logging()
logger = get_logger("test")

with set_run_id("test-run-123"):
    with set_download_id("test-dl-456"):
        logger.info("Test message", extra={{"custom_field": "custom_value"}})
        logger.warning("Password is secret123")

sleep(0.1)
shutdown_logging()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(temp_file)

    print("=== Test 1: JSON format with run_id ===")
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    assert result.returncode == 0, f"Script failed: {result.stderr}"

    # Parse and validate JSON output
    lines = [line for line in result.stdout.strip().split("\n") if line]
    # Filter to only lines with context IDs (skip "Logging initialized")
    context_lines = [line for line in lines if "Logging initialized" not in line]
    assert len(context_lines) >= 2, (
        f"Expected at least 2 log lines with context, got {len(context_lines)}"
    )

    for line in context_lines:
        log_entry = json.loads(line)
        assert log_entry["run_id"] == "test-run-123", f"run_id mismatch: {log_entry}"
        assert log_entry["download_id"] == "test-dl-456", f"download_id mismatch: {log_entry}"

    print("✓ JSON format includes run_id and download_id\n")


def test_plain_format_with_context() -> None:
    """Test plain format includes context info."""
    env = os.environ.copy()
    env["LOG_FORMAT"] = "plain"
    env["LOG_LEVEL"] = "INFO"

    script_dir = Path(__file__).parent.parent / "src"
    script = f"""
import sys
import os
sys.path.insert(0, '{script_dir}')
from getit.utils.logging import setup_logging, get_logger, set_run_id, set_download_id, shutdown_logging

setup_logging()
logger = get_logger("test")

with set_run_id("test-run-abc"):
    with set_download_id("test-dl-xyz"):
        logger.info("Test message in plain format")

# Small delay to ensure queue is drained
import time
time.sleep(0.1)
shutdown_logging()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(temp_file)

    print("=== Test 2: Plain format with context ===")
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)
    assert result.returncode == 0, f"Script failed: {result.stderr}"

    # Check for context in plain format
    assert "run_id=test-run-abc" in result.stdout, "run_id not found in plain format"
    assert "dl_id=test-dl-xyz" in result.stdout, "download_id not found in plain format"
    print("✓ Plain format includes context info\n")


def test_secret_redaction() -> None:
    """Test secrets are redacted in logs."""
    env = os.environ.copy()
    env["LOG_FORMAT"] = "json"
    env["LOG_LEVEL"] = "INFO"

    script_dir = Path(__file__).parent.parent / "src"
    script = f"""
import sys
import os
from time import sleep
sys.path.insert(0, '{script_dir}')
from getit.utils.logging import setup_logging, get_logger, shutdown_logging

setup_logging()
logger = get_logger("test")

logger.info("API key: abcdefghijklmnopqrstuvwxyz123456")
logger.info("Token: token_secret_very_long_token_here")
logger.info("Password: mypassword123")
logger.info("Authorization: Bearer secret_bearer_token_here")

sleep(0.1)
shutdown_logging()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(temp_file)

    print("=== Test 3: Secret redaction ===")
    print("STDOUT:", result.stdout)

    # Parse JSON logs and check for redaction
    lines = [line for line in result.stdout.strip().split("\n") if line]
    # Skip "Logging initialized" messages
    secret_lines = [line for line in lines if "Logging initialized" not in line]
    for line in secret_lines:
        log_entry = json.loads(line)
        message = log_entry["message"]
        assert "***REDACTED***" in message, f"Secret not redacted in: {message}"
        # Ensure original secrets are not in the message
        assert "abcdefghijklmnopqrstuvwxyz123456" not in message
        assert "token_secret_very_long_token_here" not in message
        assert "mypassword123" not in message
        assert "secret_bearer_token_here" not in message

    print("✓ Secrets are redacted in log output\n")


def test_no_color_disables_ansi() -> None:
    """Test NO_COLOR flag disables ANSI codes."""
    env = os.environ.copy()
    env["LOG_FORMAT"] = "plain"
    env["LOG_LEVEL"] = "INFO"
    env["NO_COLOR"] = "1"

    script_dir = Path(__file__).parent.parent / "src"
    script = f"""
import sys
import os
from time import sleep
sys.path.insert(0, '{script_dir}')
from getit.utils.logging import setup_logging, get_logger, shutdown_logging

setup_logging()
logger = get_logger("test")

logger.info("Plain text without colors")
logger.warning("Warning without ANSI codes")
logger.error("Error without ANSI codes")

sleep(0.1)
shutdown_logging()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(temp_file)

    print("=== Test 4: NO_COLOR disables ANSI ===")
    print("STDOUT:", result.stdout)

    # Check for ANSI escape codes
    assert "\033[" not in result.stdout, "ANSI codes found despite NO_COLOR=1"
    print("✓ NO_COLOR disables ANSI escape codes\n")


def test_non_tty_uses_json() -> None:
    """Test non-TTY output (piped) uses JSON by default."""
    env = os.environ.copy()
    env["TERM"] = "dumb"

    script_dir = Path(__file__).parent.parent / "src"
    script = f"""
import sys
import os
from time import sleep
sys.path.insert(0, '{script_dir}')
from getit.utils.logging import setup_logging, get_logger, set_run_id, shutdown_logging

setup_logging()
logger = get_logger("test")

with set_run_id("auto-detect-test"):
    logger.info("Auto-detect JSON for non-TTY")

sleep(0.1)
shutdown_logging()
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        temp_file = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_file],
            capture_output=True,
            text=True,
            env=env,
        )
    finally:
        os.unlink(temp_file)

    print("=== Test 5: Non-TTY auto-detects JSON ===")
    print("STDOUT:", result.stdout)

    # Should be JSON when piped (non-TTY)
    line = result.stdout.strip()
    try:
        log_entry = json.loads(line)
        assert log_entry["run_id"] == "auto-detect-test"
        assert "timestamp" in log_entry
        assert "level" in log_entry
        print("✓ Non-TTY output uses JSON format\n")
    except json.JSONDecodeError:
        print(f"✗ Expected JSON but got plain text: {line}")
        raise


def main() -> int:
    """Run all verification tests."""
    print("Starting structured logging verification tests\n")

    tests = [
        test_json_format_with_run_id,
        test_plain_format_with_context,
        test_secret_redaction,
        test_no_color_disables_ansi,
        test_non_tty_uses_json,
    ]

    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__} FAILED: {e}\n")
            return 1
        except Exception as e:
            print(f"✗ {test.__name__} ERROR: {e}\n")
            return 1

    print("=" * 50)
    print("All verification tests passed! ✓")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
