#!/bin/sh
set -e

# Graceful shutdown handler
_term() {
    echo "[$(date -Iseconds)] [INFO] [getit.container] Received SIGTERM, initiating graceful shutdown..." >&2
    if [ -n "$WORKER_PID" ]; then
        kill -TERM "$WORKER_PID" 2>/dev/null || true
        wait "$WORKER_PID" 2>/dev/null || true
    fi
    echo "[$(date -Iseconds)] [INFO] [getit.container] Graceful shutdown completed" >&2
    exit 0
}

trap _term SIGTERM SIGINT

# Check for --version flag (needs to be handled before getit is invoked)
if [ "$1" = "--version" ] || [ "$1" = "-V" ]; then
    exec getit --version
fi

# Route to appropriate mode based on first argument
case "$1" in
    worker)
        shift
        exec getit download "$@"
        ;;
    tui|download|info|config|supported)
        exec getit "$@"
        ;;
    help|--help|-h)
        exec getit --help
        ;;
    *)
        exec getit download "$@"
        ;;
esac
