"""MCP prompts for guiding download workflows.

Provides structured prompts that guide users through the download process,
including URL input, provider detection, password handling, and output directory selection.
"""

from __future__ import annotations

from getit.mcp.server import mcp


@mcp.prompt(name="download_workflow")
def download_workflow() -> str:
    """Guide through a complete download workflow.

    Returns a structured prompt that walks users through the download process step-by-step.
    """
    return """# Download Workflow

Follow these steps to complete a download:

## Step 1: URL Input
- Provide the file/folder URL from a supported hosting provider
- Supported providers: GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz

## Step 2: Provider Detection
- The system will detect the hosting provider from the URL
- If not recognized, you will be prompted to specify the provider manually

## Step 3: Password Handling
- If the URL requires a password, you will be prompted to enter it
- Password-protected resources will be decrypted automatically
- Leave blank if no password is required

## Step 4: Output Directory Selection
- Choose where to save the downloaded files
- Default location: ./downloads
- Specify a custom path if needed

## Step 5: Download Confirmation
- Review the download settings
- Confirm to start the download
- Download will begin with progress tracking

## Supported Features
- ✓ Single file downloads
- ✓ Folder/directory downloads
- ✓ Password-protected content
- ✓ Encrypted files (Mega.nz)
- ✓ Resume interrupted downloads
- ✓ Checksum verification

## Next Steps
1. Use the `download` tool with your URL
2. Monitor progress with `get_download_status`
3. Cancel if needed with `cancel_download`
"""
