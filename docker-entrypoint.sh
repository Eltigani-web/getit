#!/bin/sh
set -e

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
