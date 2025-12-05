#!/bin/bash
# Interactive test for kubectl-marimo plugin
# Usage: ./scripts/test-plugin-live.sh [example] [edit|run] [--source=URI]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PLUGIN_DIR="$PROJECT_DIR/plugin"
EXAMPLES_DIR="$PROJECT_DIR/plugin/examples"

# Plugin command
marimo() {
    cd "$PLUGIN_DIR" && uv run kubectl-marimo "$@"
}

# Parse all args - detect flags vs mode vs file
MODE="edit"
SOURCE_FLAG=""
FILE=""

for arg in "$@"; do
    case "$arg" in
        --source=*)
            SOURCE_FLAG="$arg"
            ;;
        edit|run)
            MODE="$arg"
            ;;
        -*)
            # Other flags, ignore
            ;;
        *)
            # First non-flag arg is the file
            if [ -z "$FILE" ]; then
                FILE="$arg"
            fi
            ;;
    esac
done

# If no file and no source, show help
if [ -z "$FILE" ] && [ -z "$SOURCE_FLAG" ]; then
    echo "Usage: $0 [example] [edit|run] [--source=URI]"
    echo ""
    echo "Examples:"
    ls -1 "$EXAMPLES_DIR"/*.{py,md} 2>/dev/null | xargs -n1 basename
    echo ""
    echo "Or specify a path: $0 /path/to/notebook.py"
    echo ""
    echo "With SSHFS mount: $0 basic.py edit --source=sshfs://user@host:/data"
    echo ""
    echo "Source-only (directory mode): $0 --source=rsync://./examples:data"
    exit 0
fi

# Handle file resolution if provided
if [ -n "$FILE" ]; then
    ORIGINAL_FILE="$FILE"
    if [ ! -f "$FILE" ]; then
        FILE="$EXAMPLES_DIR/$ORIGINAL_FILE"
    fi

    if [ ! -f "$FILE" ]; then
        echo "Not found: $ORIGINAL_FILE"
        exit 1
    fi

    # Extract resource name from file
    BASENAME=$(basename "$FILE")
    NAME=$(echo "${BASENAME%.*}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
else
    # Source-only mode - extract name from source URI
    # e.g., rsync://./examples:data -> examples
    SOURCE_PATH="${SOURCE_FLAG#--source=}"
    SOURCE_PATH="${SOURCE_PATH#*://}"  # Remove scheme
    SOURCE_PATH="${SOURCE_PATH%%:*}"   # Remove mount point
    SOURCE_PATH="${SOURCE_PATH#./}"    # Remove leading ./
    NAME=$(echo "$SOURCE_PATH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9-]/-/g' | sed 's/--*/-/g' | sed 's/^-//;s/-$//')
fi

# Cleanup function
cleanup() {
    echo ""
    echo "Cleaning up..."
    kubectl delete marimo "$NAME" --ignore-not-found 2>/dev/null
    echo "Done"
}

# Register trap for cleanup on exit
trap cleanup EXIT

if [ -n "$FILE" ]; then
    echo "Running: kubectl-marimo $MODE $FILE $SOURCE_FLAG"
    echo "Resource name: $NAME"
    echo ""
    marimo "$MODE" "$FILE" $SOURCE_FLAG
else
    echo "Running: kubectl-marimo $MODE $SOURCE_FLAG"
    echo "Resource name: $NAME"
    echo ""
    marimo "$MODE" $SOURCE_FLAG
fi
