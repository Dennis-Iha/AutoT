"""Subprocess wrapper around the whisper.cpp CLI binary (``whisper-cli``).

Chosen over Python bindings: whisper.cpp's CLI is a well-tested, actively
maintained binary, and shelling out to it avoids fragile Python/C++ binding
compilation while still being a real, production-appropriate integration
pattern. This module is the ONE place that knows whisper.cpp's exact
command-line flags and output format, verified by reading whisper.cpp's own
source (examples/cli/cli.cpp, src/whisper.cpp) rather than guessed:

- ``-dl``/``--detect-language``: runs the encoder + language-detection head
  only and returns before decoding text (src/whisper.cpp:
  ``if (params.detect_language) return 0;`` immediately after the detection
  log line) - this is the fast LID-only path Phase 4 uses.
- The detection result is logged at INFO level (stderr, via WHISPER_LOG_INFO)
  as ``"...auto-detected language: <code> (p = <prob>)"``, regardless of
  whether detect-language-only or full transcription was requested.
- ``-oj``/``--output-json`` with ``-l auto`` writes a JSON file shaped like:
  ``{"result": {"language": "es"}, "transcription": [{"offsets": {"from":
  ms, "to": ms}, "text": "..."}]}`` (examples/cli/cli.cpp's JSON writer).

Both language_id and asr modules import this rather than each shelling out
independently, because a Whisper-family model computes language ID and
transcription from the same encoder pass - see core/language_id/whisper_lid.py.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from core.audio.wav_io import write_wav

WHISPER_SAMPLE_RATE = 16000
LANG_DETECT_RE = re.compile(r"auto-detected language:\s*(\w+)\s*\(p\s*=\s*([\d.]+)\)")


class WhisperCppError(RuntimeError):
    pass


@dataclass
class WhisperCppConfig:
    binary_path: Path
    model_path: Path
    threads: int = 4
    # Measured on the reference dev workstation (CPU-only, base multilingual
    # model, -l auto): up to ~90s for a ~2s clip in some languages - this is
    # NOT real-time and is exactly why Phase 11 (quantization) and Phase 12
    # (embedded/NPU hardware) exist; 240s gives headroom under CPU
    # contention rather than flaking under normal single-request load.
    timeout_s: float = 240.0


class WhisperCppRunner:
    """Owns one whisper.cpp binary + model pair; shells out per call."""

    def __init__(self, config: WhisperCppConfig):
        if not config.binary_path.exists():
            raise FileNotFoundError(f"whisper.cpp binary not found: {config.binary_path}")
        if not config.model_path.exists():
            raise FileNotFoundError(f"whisper.cpp model not found: {config.model_path}")
        self.config = config

    def _write_temp_wav(self, audio: np.ndarray, sample_rate_hz: int) -> Path:
        if sample_rate_hz != WHISPER_SAMPLE_RATE:
            raise ValueError(
                f"whisper.cpp requires {WHISPER_SAMPLE_RATE}Hz input, got {sample_rate_hz}Hz - "
                "resample before calling"
            )
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        tmp = Path(path)
        write_wav(tmp, audio, sample_rate_hz)
        return tmp

    def _run(self, args: list[str]) -> subprocess.CompletedProcess:
        # whisper.cpp is vendored (third_party/), not installed system-wide,
        # so its shared libs (libwhisper.so, libggml*.so) live next to the
        # binary rather than on the system loader path - point the loader
        # at that directory explicitly rather than requiring the caller's
        # shell to have it set.
        env = {**os.environ, "LD_LIBRARY_PATH": str(self.config.binary_path.parent)}
        return subprocess.run(
            args, capture_output=True, text=True, timeout=self.config.timeout_s, env=env, check=False
        )

    def detect_language(self, audio: np.ndarray, sample_rate_hz: int) -> tuple[str, float]:
        """Returns (language_code, probability). Fast path: encoder-only, no decode."""
        wav_path = self._write_temp_wav(audio, sample_rate_hz)
        try:
            args = [
                str(self.config.binary_path),
                "-m", str(self.config.model_path),
                "-f", str(wav_path),
                "-dl",
                "-t", str(self.config.threads),
            ]
            result = self._run(args)
            combined = result.stdout + "\n" + result.stderr
            match = LANG_DETECT_RE.search(combined)
            if not match:
                raise WhisperCppError(
                    f"could not parse language detection output (exit={result.returncode}); "
                    f"stderr tail: {result.stderr[-500:]}"
                )
            return match.group(1), float(match.group(2))
        finally:
            wav_path.unlink(missing_ok=True)

    def transcribe(self, audio: np.ndarray, sample_rate_hz: int, language: str | None = None) -> dict:
        """Full transcription. Returns the parsed whisper.cpp JSON output dict."""
        wav_path = self._write_temp_wav(audio, sample_rate_hz)
        out_prefix = wav_path.with_suffix("")
        json_path = out_prefix.with_name(out_prefix.name + ".json")
        try:
            args = [
                str(self.config.binary_path),
                "-m", str(self.config.model_path),
                "-f", str(wav_path),
                "-l", language or "auto",
                "-oj",
                "-of", str(out_prefix),
                "-t", str(self.config.threads),
            ]
            result = self._run(args)
            if not json_path.exists():
                raise WhisperCppError(
                    f"whisper-cli did not produce JSON output (exit={result.returncode}); "
                    f"stderr tail: {result.stderr[-500:]}"
                )
            with open(json_path) as f:
                return json.load(f)
        finally:
            wav_path.unlink(missing_ok=True)
            json_path.unlink(missing_ok=True)
