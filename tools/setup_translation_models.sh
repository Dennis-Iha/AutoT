#!/usr/bin/env bash
# Downloads Argos Translate's .argosmodel packages for <lang>->en and
# extracts the CTranslate2 model + tokenizer files AT actually uses -
# deliberately discarding the bundled stanza/*.pt sentence-splitter model
# each package ships, since AT already segments utterances upstream via
# core/vad/segmenter.py (Phase 2) and stanza would pull in a PyTorch
# dependency for no benefit here.
#
# Package layout is NOT uniform across versions (verified by inspection,
# not assumed): package v1.0 (ar) ships model/shared_vocabulary.txt +
# sentencepiece.model; v1.9 packages ship model/shared_vocabulary.json +
# model/config.json, and use EITHER sentencepiece.model (bn/zh/fr/hi/pt/ru)
# OR the older subword-nmt BPE format as bpe.model (es) - CTranslate2 reads
# whichever vocabulary file is in model/ automatically, so this script just
# copies the whole model/ directory rather than hardcoding a filename, and
# copies whichever of sentencepiece.model/bpe.model is present so
# core/translation/ctranslate2_translator.py can detect which tokenizer to
# use per language pair.
#
# Usage: tools/setup_translation_models.sh [lang ...]
#   e.g. tools/setup_translation_models.sh ar es fr
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="$REPO_ROOT/models/translation/argos"

declare -A PACKAGE_VERSION=(
    [ar]="1_0" [bn]="1_9" [zh]="1_9" [fr]="1_9"
    [hi]="1_1" [pt]="1_9" [ru]="1_9" [es]="1_9"
)

if [ "$#" -eq 0 ]; then
    LANGS=(ar bn zh fr hi pt ru es)
else
    LANGS=("$@")
fi

mkdir -p "$DEST_ROOT"
for lang in "${LANGS[@]}"; do
    version="${PACKAGE_VERSION[$lang]:-}"
    if [ -z "$version" ]; then
        echo "warning: no known Argos package for '$lang', skipping" >&2
        continue
    fi
    dest_dir="$DEST_ROOT/${lang}_en"
    if [ -f "$dest_dir/model/model.bin" ]; then
        echo "Already present: $dest_dir"
        continue
    fi

    url="https://argos-net.com/v1/translate-${lang}_en-${version}.argosmodel"
    tmp_zip="$(mktemp --suffix=.argosmodel)"
    echo "Downloading $lang -> en ($url)..."
    curl -sL -o "$tmp_zip" "$url"

    tmp_extract="$(mktemp -d)"
    unzip -q "$tmp_zip" -d "$tmp_extract"
    pkg_dir="$(find "$tmp_extract" -mindepth 1 -maxdepth 1 -type d)"

    mkdir -p "$dest_dir"
    cp -r "$pkg_dir/model" "$dest_dir/model"
    [ -f "$pkg_dir/sentencepiece.model" ] && cp "$pkg_dir/sentencepiece.model" "$dest_dir/sentencepiece.model"
    [ -f "$pkg_dir/bpe.model" ] && cp "$pkg_dir/bpe.model" "$dest_dir/bpe.model"

    rm -rf "$tmp_zip" "$tmp_extract"
    echo "Installed: $dest_dir ($(du -sh "$dest_dir" | cut -f1))"
done

echo "Done. $(ls "$DEST_ROOT" 2>/dev/null | wc -l) language pair(s) installed under $DEST_ROOT"
