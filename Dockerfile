# Dockerfile for getit CLI - Universal file hosting downloader

# Build stage
FROM python:3.11-slim AS builder

# Set build-time environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libxml2-dev \
        libxslt-dev \
        pkg-config \
        && rm -rf /var/lib/apt/lists/*

# Copy project files (include .git for VCS version detection)
COPY .git .git/
COPY pyproject.toml MANIFEST.in ./
COPY src/ ./src/

# Copy pyproject.toml fix script
COPY docker-fix-pyproject.sh ./

# Derive version from git and inject into pyproject.toml
RUN chmod +x docker-fix-pyproject.sh && ./docker-fix-pyproject.sh

# Create virtual environment and install package
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel && \
    /opt/venv/bin/pip install --no-cache-dir . && \
    cat /tmp/getit_version > /opt/venv/VERSION

# Runtime stage
FROM python:3.11-slim

# Copy VERSION file first to use in LABEL
COPY --from=builder /opt/venv/VERSION /tmp/VERSION

# Set labels (version is derived from git during build)
LABEL maintainer="getit contributors" \
      description="Universal file hosting downloader with TUI"

# Set runtime environment variables with TTY-safe defaults
# TTY detection in containers defaults to false, so use JSON logging
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Concurrency configuration
    GETIT_MAX_CONCURRENT_DOWNLOADS=3 \
    # Logging configuration (JSON for non-TTY/container environments)
    LOG_FORMAT=json \
    LOG_LEVEL=INFO \
    NO_COLOR=1 \
    # Download directory
    GETIT_DOWNLOAD_DIR=/data/downloads

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Create non-root user with fixed UID (simpler approach)
RUN useradd -u 999 -U -m -d /home/getit -s /sbin/nologin getit && \
    mkdir -p /home/getit /data/downloads && \
    chown -R 999:999 /home/getit /data

# Copy virtual environment from builder
COPY --from=builder --chown=getit:getit /opt/venv /opt/venv

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh && \
    chown getit:getit /usr/local/bin/docker-entrypoint.sh

# Set working directory
WORKDIR /home/getit

# Switch to non-root user
USER getit

# Healthcheck - verify the CLI is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD getit --version || exit 1

# Expose port (not used for network services, but good practice)
EXPOSE 8080

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command is to start in worker mode
CMD ["worker"]
