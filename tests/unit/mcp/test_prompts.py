"""Tests for MCP prompts registration and functionality."""

from __future__ import annotations

import pytest

from getit.mcp.prompts import download_workflow
from getit.mcp.server import mcp


class TestDownloadWorkflowPrompt:
    def test_download_workflow_returns_string(self):
        """Verify download_workflow returns a non-empty string."""
        result = download_workflow()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_download_workflow_contains_workflow_steps(self):
        """Verify prompt contains key workflow steps."""
        result = download_workflow()
        assert "URL Input" in result
        assert "Provider Detection" in result
        assert "Password Handling" in result
        assert "Output Directory" in result
        assert "Download Confirmation" in result

    def test_download_workflow_mentions_supported_providers(self):
        """Verify prompt mentions all supported providers."""
        result = download_workflow()
        providers = ["GoFile", "PixelDrain", "MediaFire", "1Fichier", "Mega.nz"]
        for provider in providers:
            assert provider in result

    def test_download_workflow_includes_tool_references(self):
        """Verify prompt mentions available tools."""
        result = download_workflow()
        assert "download" in result
        assert "get_download_status" in result
        assert "cancel_download" in result

    @pytest.mark.asyncio
    async def test_download_workflow_prompt_registered(self):
        """Verify download_workflow prompt is registered with mcp."""
        prompts = await mcp.list_prompts()
        prompt_names = [p.name for p in prompts]
        assert "download_workflow" in prompt_names

    @pytest.mark.asyncio
    async def test_download_workflow_prompt_has_metadata(self):
        """Verify download_workflow prompt has proper metadata."""
        prompts = await mcp.list_prompts()
        workflow_prompt = None
        for p in prompts:
            if p.name == "download_workflow":
                workflow_prompt = p
                break

        assert workflow_prompt is not None
        assert workflow_prompt.name == "download_workflow"

    @pytest.mark.asyncio
    async def test_get_prompt_returns_download_workflow(self):
        """Verify get_prompt method returns download_workflow content."""
        result = await mcp.get_prompt("download_workflow")
        assert result is not None
        assert hasattr(result, "messages")
        assert len(result.messages) > 0

    def test_download_workflow_is_concise_but_complete(self):
        """Verify prompt is structured and not overly verbose."""
        result = download_workflow()
        lines = result.strip().split("\n")
        assert 20 <= len(lines) <= 100
        assert "##" in result or "#" in result
