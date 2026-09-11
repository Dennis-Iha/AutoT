#!/usr/bin/env bash
# Clones and builds whisper.cpp into third_party/whisper.cpp (gitignored -
# this is a vendored external dependency, not repo source). Idempotent:
# re-running pulls the latest commit on an existing clone and rebuilds.
#
# Usage: tools/setup_whisper_cpp.sh [model ...]
#   e.g. tools/setup_whisper_cpp.sh tiny base
# Downloads ggml multilingual models (NOT the .en-suffixed English-only
# ones - AT needs all 9 initial languages) into models/asr/whisper/.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THIRD_PARTY="$REPO_ROOT/third_party/whisper.cpp"
MODELS_DIR="$REPO_ROOT/models/asr/whisper"

if [ -d "$THIRD_PARTY/.git" ]; then
    echo "Updating existing whisper.cpp clone..."
    git -C "$THIRD_PARTY" pull --ff-only
else
    echo "Cloning whisper.cpp..."
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$THIRD_PARTY"
fi

echo "Configuring (CMake)..."
cmake -B "$THIRD_PARTY/build" -S "$THIRD_PARTY" \
    -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON

echo "Building (this compiles the whisper.cpp library + CLI, several minutes on first build)..."
cmake --build "$THIRD_PARTY/build" -j"$(nproc)" --config Release

BINARY="$THIRD_PARTY/build/bin/whisper-cli"
if [ ! -x "$BINARY" ]; then
    echo "error: build did not produce $BINARY" >&2
    exit 1
fi
echo "Built: $BINARY"

mkdir -p "$MODELS_DIR"
if [ "$#" -eq 0 ]; then
    MODELS=(tiny base)
else
    MODELS=("$@")
fi
for size in "${MODELS[@]}"; do
    dest="$MODELS_DIR/ggml-${size}.bin"
    if [ -f "$dest" ]; then
        echo "Model already present: $dest"
        continue
    fi
    echo "Downloading multilingual ggml-${size}.bin..."
    curl -sL -o "$dest" "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${size}.bin"
done

echo "Done. Binary: $BINARY"
echo "Models: $(ls "$MODELS_DIR")"
