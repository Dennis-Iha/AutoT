"""Phase 10: AT Offline Runtime CLI - verifies every model needed for a
given set of languages is present and (optionally) checksum-valid, with a
clear PASS/FAIL report instead of letting a missing/corrupted model surface
as a confusing crash deep inside whisper.cpp/ctranslate2/onnxruntime.

Usage:
    python -m tools.check_offline_readiness --languages ar bn zh fr hi pt ru es en
    python -m tools.check_offline_readiness --languages es --no-checksums  # fast, existence-only
"""

from __future__ import annotations

import argparse

from core.common.offline_runtime import check_offline_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--languages", nargs="+", default=["en", "zh", "hi", "es", "ar", "fr", "bn", "pt", "ru"])
    parser.add_argument("--target", default="en")
    parser.add_argument("--asr-model", default=None, help="e.g. whisper-tiny, whisper-base (default: config)")
    parser.add_argument("--tts-voice", default=None)
    parser.add_argument("--no-checksums", action="store_true", help="skip full checksum verification (faster)")
    args = parser.parse_args()

    report = check_offline_readiness(
        languages=args.languages,
        target_language=args.target,
        asr_model_id=args.asr_model,
        tts_voice_id=args.tts_voice,
        verify_checksums=not args.no_checksums,
    )

    for check in report.checks:
        status = "OK  " if check.ok else "FAIL"
        print(f"  [{status}] {check.component}: {check.detail}")

    if report.ready:
        print(f"\nREADY: all {len(report.checks)} check(s) passed - fully offline-capable for {args.languages} -> {args.target}")
        return 0
    else:
        print(f"\nNOT READY: {len(report.issues())}/{len(report.checks)} check(s) failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
