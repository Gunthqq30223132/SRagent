#!/bin/bash
# Nightly incremental sync script for the offline knowledge base system

set -euo pipefail

# Target corpus directory defaulting to /Volumes/Gun SSD/1. STUDY/
TARGET_DIR="${1:-/Volumes/Gun SSD/1. STUDY/}"

echo "Starting nightly sync for corpus directory: $TARGET_DIR"

if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Target directory '$TARGET_DIR' does not exist."
    exit 1
fi

# Find all PDF files recursively and run the ingestion process
find "$TARGET_DIR" -type f -name "*.pdf" -print0 | while IFS= read -r -d '' pdf_file; do
    echo "Ingesting: $pdf_file"
    python -m tools.warehouse.ingest_pdf "$pdf_file"
done

echo "Nightly sync complete."
