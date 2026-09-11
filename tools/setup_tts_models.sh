#!/usr/bin/env bash
# Downloads Piper TTS voice models (ONNX, MIT-licensed, from
# rhasspy/piper-voices on HuggingFace). Piper bundles its own espeak-ng
# phonemization data (no separate espeak-ng install needed at runtime).
#
# Verifies each download's size against the server's Content-Length before
# accepting it - added after a real truncated download was caught during
# development (a parallel curl silently produced a 27MB file for a 63MB
# model; onnxruntime failed with "Protobuf parsing failed" rather than a
# clear "incomplete download" error, so don't trust file presence alone).
#
# Usage: tools/setup_tts_models.sh [voice ...]
#   e.g. tools/setup_tts_models.sh en_US-amy-medium
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="$REPO_ROOT/models/tts/piper"
BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

declare -A VOICE_PATH=(
    [en_US-amy-medium]="en/en_US/amy/medium/en_US-amy-medium"
)

if [ "$#" -eq 0 ]; then
    VOICES=(en_US-amy-medium)
else
    VOICES=("$@")
fi

download_verified() {
    local url="$1" dest="$2"
    local expected_size
    expected_size=$(curl -sIL "$url" | grep -i '^content-length:' | tail -1 | tr -d '\r' | awk '{print $2}')
    curl -sL -o "$dest" "$url"
    local actual_size
    actual_size=$(stat -c%s "$dest")
    if [ -n "$expected_size" ] && [ "$actual_size" != "$expected_size" ]; then
        echo "error: $dest truncated (got $actual_size bytes, expected $expected_size)" >&2
        rm -f "$dest"
        return 1
    fi
}

mkdir -p "$DEST_ROOT"
for voice in "${VOICES[@]}"; do
    rel="${VOICE_PATH[$voice]:-}"
    if [ -z "$rel" ]; then
        echo "warning: no known Piper voice '$voice', skipping" >&2
        continue
    fi
    dest_dir="$DEST_ROOT/$voice"
    if [ -f "$dest_dir/$voice.onnx" ]; then
        echo "Already present: $dest_dir"
        continue
    fi
    mkdir -p "$dest_dir"
    echo "Downloading $voice..."
    download_verified "$BASE_URL/${rel}.onnx" "$dest_dir/$voice.onnx"
    download_verified "$BASE_URL/${rel}.onnx.json" "$dest_dir/$voice.onnx.json"
    echo "Installed: $dest_dir ($(du -sh "$dest_dir" | cut -f1))"
done

echo "Done. $(ls "$DEST_ROOT" 2>/dev/null | wc -l) voice(s) installed under $DEST_ROOT"
