#!/usr/bin/env bash
# Phase 11: produces quantized variants of an installed ggml ASR model using
# whisper.cpp's own whisper-quantize tool (built alongside whisper-cli by
# tools/setup_whisper_cpp.sh). Output goes in models/asr/whisper/quantized/
# (gitignored, same as the source models) so tools/quantization_benchmark.py
# has real quantized models to measure rather than estimating anything.
#
# Usage: tools/quantize_asr_models.sh [source_model] [quant_type ...]
#   e.g. tools/quantize_asr_models.sh base q4_0 q5_0 q8_0
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QUANTIZE_BIN="$REPO_ROOT/third_party/whisper.cpp/build/bin/whisper-quantize"
MODELS_DIR="$REPO_ROOT/models/asr/whisper"
OUT_DIR="$MODELS_DIR/quantized"

if [ ! -x "$QUANTIZE_BIN" ]; then
    echo "error: $QUANTIZE_BIN not found - run tools/setup_whisper_cpp.sh first" >&2
    exit 1
fi

SOURCE_SIZE="${1:-base}"
shift || true
if [ "$#" -eq 0 ]; then
    TYPES=(q4_0 q5_0 q8_0)
else
    TYPES=("$@")
fi

SOURCE_MODEL="$MODELS_DIR/ggml-${SOURCE_SIZE}.bin"
if [ ! -f "$SOURCE_MODEL" ]; then
    echo "error: $SOURCE_MODEL not found - run tools/setup_whisper_cpp.sh first" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
export LD_LIBRARY_PATH="$REPO_ROOT/third_party/whisper.cpp/build/bin"
for type in "${TYPES[@]}"; do
    dest="$OUT_DIR/ggml-${SOURCE_SIZE}-${type}.bin"
    if [ -f "$dest" ]; then
        echo "Already present: $dest"
        continue
    fi
    echo "Quantizing $SOURCE_SIZE -> $type..."
    "$QUANTIZE_BIN" "$SOURCE_MODEL" "$dest" "$type"
    echo "  $(du -h "$dest" | cut -f1)  $dest"
done

echo "Done."
