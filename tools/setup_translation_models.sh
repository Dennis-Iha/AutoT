#!/usr/bin/env bash
# Downloads Argos Translate's .argosmodel packages for a given language
# pair and extracts the CTranslate2 model + tokenizer files AT actually
# uses - deliberately discarding the bundled stanza/*.pt sentence-splitter
# model each package ships, since AT already segments utterances upstream
# via core/vad/segmenter.py (Phase 2) and stanza would pull in a PyTorch
# dependency for no benefit here.
#
# Package layout is NOT uniform across versions (verified by inspection,
# not assumed): package v1.0 ships model/shared_vocabulary.txt +
# sentencepiece.model; v1.9 packages ship model/shared_vocabulary.json +
# model/config.json, and use EITHER sentencepiece.model OR the older
# subword-nmt BPE format as bpe.model (this affects es->en and en->es
# specifically, both v1.0) - CTranslate2 reads whichever vocabulary file is
# in model/ automatically, so this script just copies the whole model/
# directory rather than hardcoding a filename, and copies whichever of
# sentencepiece.model/bpe.model is present so
# core/translation/ctranslate2_translator.py can detect which tokenizer to
# use per language pair.
#
# Usage: tools/setup_translation_models.sh [pair ...]
#   pair is "SRC-TGT", e.g. es-en or en-es. Defaults to all 16 pairs
#   covering both directions between English and the other 8 v1 languages
#   (Phase 17 Conversation Mode needs both directions; Phase 6's original
#   scope only needed X->en).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST_ROOT="$REPO_ROOT/models/translation/argos"

declare -A PACKAGE_VERSION=(
    [ar-en]="1_0" [bn-en]="1_9" [zh-en]="1_9" [fr-en]="1_9"
    [hi-en]="1_1" [pt-en]="1_9" [ru-en]="1_9" [es-en]="1_9"
    [en-ar]="1_0" [en-bn]="1_9" [en-zh]="1_9" [en-fr]="1_9"
    [en-hi]="1_1" [en-pt]="1_9" [en-ru]="1_9" [en-es]="1_0"
)

if [ "$#" -eq 0 ]; then
    PAIRS=(ar-en bn-en zh-en fr-en hi-en pt-en ru-en es-en
           en-ar en-bn en-zh en-fr en-hi en-pt en-ru en-es)
else
    PAIRS=("$@")
fi

mkdir -p "$DEST_ROOT"
for pair in "${PAIRS[@]}"; do
    version="${PACKAGE_VERSION[$pair]:-}"
    if [ -z "$version" ]; then
        echo "warning: no known Argos package for '$pair', skipping" >&2
        continue
    fi
    src="${pair%-*}"
    tgt="${pair#*-}"
    dest_dir="$DEST_ROOT/${src}_${tgt}"
    if [ -f "$dest_dir/model/model.bin" ]; then
        echo "Already present: $dest_dir"
        continue
    fi

    url="https://argos-net.com/v1/translate-${src}_${tgt}-${version}.argosmodel"
    tmp_zip="$(mktemp --suffix=.argosmodel)"
    echo "Downloading $src -> $tgt ($url)..."
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
