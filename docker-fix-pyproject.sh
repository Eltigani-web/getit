#!/bin/bash
# docker-fix-pyproject.sh
# Derives version from git tags via setuptools_scm logic and injects into pyproject.toml
# This allows Docker builds to have proper versioning without requiring setuptools_scm at runtime

set -e

# Get version from git describe (matches setuptools_scm behavior)
if git describe --tags --always >/dev/null 2>&1; then
    RAW_VERSION=$(git describe --tags --always)
    # Convert git describe output to PEP 440 compatible version
    # v0.1.0 -> 0.1.0
    # v0.1.0-14-g06ced5c -> 0.1.0.dev14+g06ced5c
    VERSION=$(echo "$RAW_VERSION" | sed -E 's/^v//; s/-([0-9]+)-g([a-f0-9]+)$/.dev\1+\2/')
else
    # Fallback if no git info available
    VERSION="0.1.0"
fi

echo "Detected version: $VERSION"

# Create a modified pyproject.toml with static version for Docker build
# Remove dynamic = ["version"] and add explicit version
python3 << PYEOF
import re

with open('pyproject.toml', 'r') as f:
    content = f.read()

# Remove dynamic = ["version"] line
content = re.sub(r'^dynamic\s*=\s*\["version"\]\n', '', content, flags=re.MULTILINE)

# Add version after name line
content = re.sub(
    r'(name\s*=\s*"getit-cli")',
    f'\\1\nversion = "$VERSION"',
    content
)

# Remove [tool.hatch.version] section entirely (not needed with static version)
content = re.sub(
    r'\[tool\.hatch\.version\][^\[]*',
    '',
    content,
    flags=re.DOTALL
)

with open('pyproject.toml', 'w') as f:
    f.write(content)

print(f"Updated pyproject.toml with version: $VERSION")
PYEOF

# Export version for use in Dockerfile ARG
echo "$VERSION" > /tmp/getit_version
