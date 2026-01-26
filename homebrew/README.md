# Homebrew Tap for getit

This directory contains the Homebrew formula for getit.

## Setting up a Homebrew Tap

1. Create a new GitHub repository named `homebrew-getit`
2. Copy the formula to the repository:
   ```bash
   cp homebrew/getit.rb /path/to/homebrew-getit/Formula/getit.rb
   ```
3. Update the SHA256 checksums after publishing to PyPI
4. Push to GitHub

## Installation

Users can then install with:
```bash
brew tap yourusername/getit
brew install getit
```

## Updating the Formula

After publishing a new version to PyPI:

1. Get the new tarball URL from PyPI
2. Calculate SHA256: `curl -sL URL | shasum -a 256`
3. Update the formula with new version and SHA256
4. Update resource SHA256 values as needed
