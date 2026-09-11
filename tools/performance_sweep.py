"""Phase 30: one consolidated performance sweep - runs the REAL full
pipeline (LID -> ASR -> translation -> TTS, core/orchestration/pipeline.py)
across all 9 v1 languages and reports an honest per-language pass/fail,
rather than the per-stage benchmarks earlier phases already have
(tools/asr_benchmark.py, tools/translation_benchmark.py,
tools/tts_benchmark.py, tools/language_id_benchmark.py measure ASR/
translation/TTS/LID in isolation - this measures whether a language
actually produces a working end-to-end translation TODAY, the number that
actually matters to a user).

Like every other benchmark in this project, this runs against
tests/fixtures/speech/ - espeak-ng SYNTHESIZED speech, not natural human
recordings (see the fixtures' own "_provenance" field). Phase 8 already
found LID accuracy on these fixtures is only 2-3/9 languages reliable; this
sweep is expected to surface the same gap at the full-pipeline level, and
reports it honestly rather than only running the languages known to pass.

"...across all 9 languages/environments" per the master spec: this script
covers the LANGUAGES half for real. The ENVIRONMENTS half (background
noise, different microphones/rooms, real device conditions) is NOT covered
here - there are no real-environment recordings or physical hardware in
this development environment to test that against. Flagged as an open gap,
not silently dropped.

Optionally reports each real result to Phase 31's metrics backend
(--report-to/--token/--device-id) as one aggregate, content-free
MetricEvent per language (status + language pair + latency only - never
transcript/translation text, matching MetricEventCreate's schema) - this is
how tools/metrics_report.py's "dashboard" gets genuinely real data without
a device fleet: from this project's own real pipeline runs, not fabricated.

Usage:
    python -m tools.performance_sweep [--out results.json]
    python -m tools.performance_sweep --report-to http://127.0.0.1:8000 \\
        --token <jwt> --device-id <id>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from core.asr.whisper_cpp_asr import WhisperCppASR
from core.audio.wav_io import read_wav
from core.common.config import REPO_ROOT, load_config
from core.language_id.whisper_lid import WhisperLanguageIdentifier
from core.orchestration.pipeline import TranslationPipeline
from core.translation.ctranslate2_translator import CTranslate2TranslationEngine
from core.translation.model_registry import TranslationModelRegistry
from core.tts.piper_tts import PiperTTSEngine
from core.tts.voice_registry import VoiceRegistry

FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "speech"


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else REPO_ROOT / path


def _report_event(base_url: str, token: str, device_id: str, row: dict) -> None:
    import httpx  # lazy: only needed when --report-to is used, keeps the base tool dependency-light

    httpx.post(
        f"{base_url}/devices/{device_id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "event_type": "translation_attempt",
            "status": row["status"],
            "source_language": row["detected_language"],
            "target_language": "en",
            "total_latency_ms": row["total_latency_ms"],
        },
        timeout=10.0,
    ).raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--report-to", default=None, help="AT backend base URL to also POST results to")
    parser.add_argument("--token", default=None, help="JWT from POST /auth/login (required with --report-to)")
    parser.add_argument("--device-id", default=None, help="required with --report-to")
    args = parser.parse_args()
    if args.report_to and not (args.token and args.device_id):
        print("--report-to requires --token and --device-id", file=sys.stderr)
        return 1

    cfg = load_config().asr
    binary_path = _resolve(cfg.binary_path)
    model_path = _resolve(cfg.model_path)
    if not binary_path.exists() or not model_path.exists():
        print(f"whisper.cpp not set up: binary={binary_path} model={model_path}")
        print("Run tools/setup_whisper_cpp.sh first.")
        return 1

    translation_registry = TranslationModelRegistry.load()
    tts_registry = VoiceRegistry.load()
    translation_ready = any(
        translation_entry.is_ready()
        for s, t in translation_registry.pairs()
        if (translation_entry := translation_registry.get(s, t))
    )
    if not translation_ready:
        print("no translation models installed - run tools/setup_translation_models.sh first")
        return 1
    tts_ready = any(
        voice_entry.is_ready() for v in tts_registry.voice_ids() if (voice_entry := tts_registry.get(v))
    )
    if not tts_ready:
        print("no TTS voices installed - run tools/setup_tts_models.sh first")
        return 1

    with open(FIXTURES_DIR / "manifest.json") as f:
        manifest = json.load(f)
    languages = sorted(lang for lang, entry in manifest.items() if isinstance(entry, dict))

    pipeline = TranslationPipeline(
        language_identifier=WhisperLanguageIdentifier(binary_path, model_path),
        asr_engine=WhisperCppASR(binary_path, model_path),
        translation_engine=CTranslate2TranslationEngine(translation_registry),
        tts_engine=PiperTTSEngine(tts_registry),
        target_language="en",
    )

    rows = []
    passed = 0
    for lang in languages:
        audio, sr = read_wav(FIXTURES_DIR / f"{lang}.wav")
        start = time.perf_counter()
        result = pipeline.process(audio, sr)
        total_latency_ms = (time.perf_counter() - start) * 1000.0
        ok = result.ok
        passed += ok
        detected = result.detected_language.language if result.detected_language else None
        # A real, dangerous failure mode this sweep exists to catch: LID can
        # be confidently WRONG (>=0.5, the pipeline's threshold) about a
        # non-English utterance actually being English. When that happens,
        # source==target, translation is skipped entirely (by design, for
        # genuine English input), and whatever whisper.cpp's English-forced
        # decode hallucinates gets spoken back as if it were a legitimate
        # response - status is "ok" but the output is garbage, not a
        # graceful failure like LOW_CONFIDENCE. Flagged explicitly rather
        # than counted as an unqualified pass.
        suspect_misdetected_as_target = (
            result.ok and result.translation is None and detected != lang and lang != "en"
        )
        rows.append({
            "language": lang,
            "status": result.status,
            "detected_language": detected,
            "lid_confidence": round(result.detected_language.confidence, 4) if result.detected_language else None,
            "transcription": result.transcription.text if result.transcription else None,
            "translation": result.translation.text if result.translation else None,
            "suspect_misdetected_as_target": suspect_misdetected_as_target,
            "total_latency_ms": round(total_latency_ms, 1),
            "stage_latencies_ms": {k: round(v, 1) for k, v in result.stage_latencies_ms.items()},
        })
        flag = "  <-- SUSPECT: detected as target language but wasn't" if suspect_misdetected_as_target else ""
        print(f"  {lang:3s} [{result.status:20s}] "
              f"lid={detected or '?':3s} "
              f"conf={result.detected_language.confidence if result.detected_language else 0:.2f} "
              f"{total_latency_ms/1000:.1f}s "
              f"{'-> ' + repr(result.translation.text) if result.translation else ''}{flag}")

        if args.report_to:
            try:
                _report_event(args.report_to, args.token, args.device_id, rows[-1])
            except Exception as e:  # noqa: BLE001 - reporting must never abort the sweep itself
                print(f"    (metrics reporting failed, continuing sweep: {e})", file=sys.stderr)

    n_suspect = sum(r["suspect_misdetected_as_target"] for r in rows)
    n_genuinely_correct = passed - n_suspect
    pass_rate = passed / len(languages)
    genuine_rate = n_genuinely_correct / len(languages)
    print(f"\nRaw pipeline-status pass rate: {passed}/{len(languages)} ({pass_rate:.0%})")
    if n_suspect:
        print(f"Of those, {n_suspect} are SUSPECT (confidently misdetected as the target "
              "language, so translation was skipped and garbage was spoken back as if valid) - "
              f"NOT genuine passes. Genuinely-correct rate: {n_genuinely_correct}/{len(languages)} ({genuine_rate:.0%}).")
    print("Per docs/architecture.md's 'Language coverage is a claim, not an assumption' section: "
          "only languages reported OK here AND not flagged SUSPECT have any evidence of working end-to-end today.")

    report = {
        "asr_model": model_path.name,
        "pass_rate_raw_status": pass_rate,
        "pass_rate_genuinely_correct": genuine_rate,
        "n_languages": len(languages),
        "n_passed_raw_status": passed,
        "n_suspect_misdetected_as_target": n_suspect,
        "n_genuinely_correct": n_genuinely_correct,
        "rows": rows,
        "caveat_languages": "measured on espeak-ng synthesized speech, not natural human speech",
        "caveat_environments": (
            "no real-environment (noise/room/device) testing performed - "
            "requires physical hardware this environment doesn't have (Phase 22-28)"
        ),
        "caveat_suspect_metric": (
            "a row is SUSPECT when status=ok, no translation occurred (source appeared to equal "
            "target), yet the detected language does not match the fixture's true language - i.e. "
            "LID was confidently wrong in exactly the way that skips translation instead of "
            "triggering the LOW_CONFIDENCE safeguard. These are worse than LOW_CONFIDENCE failures: "
            "they produce plausible-looking but meaningless output rather than failing visibly."
        ),
    }
    if args.out:
        args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
