"""Phase 3 benchmark: measures the objective effect of each audio cleanup
algorithm on synthetic signals with known ground truth, and specifically
whether noise suppression reduces the VAD false-positive-on-tone problem
documented in tests/vad/test_webrtc_vad.py::test_loud_pure_tone_is_misclassified_as_speech.

ASR does not exist yet (Phase 5), so "benchmark the effect on ASR accuracy"
from the master spec is not yet possible to measure honestly - this
benchmarks the effect on the metrics that ARE currently measurable (SNR,
ERLE, reverberant tail energy, beamforming array gain) plus the one real
downstream consumer that exists today (VAD). Re-run this once Phase 5 lands
to add WER-based numbers.

Usage:
    python -m tools.audio_cleanup_benchmark [--out results.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from core.beamforming.delay_sum import DelaySumBeamformer
from core.denoise.dereverberation import SpectralDereverberator
from core.denoise.echo_cancellation import NLMSEchoCanceller
from core.denoise.noise_suppression import SpectralSubtractionNoiseSuppressor
from core.vad.webrtc_vad import WebRtcVAD

SR = 16000


def _db(power: float) -> float:
    return 10 * np.log10(max(power, 1e-12))


def _tone(t: np.ndarray, freqs=(200, 400, 800), amp=3000) -> np.ndarray:
    return sum(np.sin(2 * np.pi * f * t) for f in freqs) * amp / len(freqs)


def bench_noise_suppression() -> list[dict]:
    results = []
    for noise_std in (200, 500, 1000):
        rng = np.random.default_rng(42)
        n = int(2.0 * SR)
        t = np.arange(n) / SR
        speech_region = (t >= 0.5) & (t < 1.5)
        speech = np.zeros(n)
        speech[speech_region] = _tone(t)[speech_region]
        noise = rng.normal(0, noise_std, n)
        mixture = np.clip(speech + noise, -32768, 32767).astype(np.int16)

        cleaned = SpectralSubtractionNoiseSuppressor().process(mixture, SR).astype(np.float64)
        noise_only = ~speech_region
        in_rms = np.sqrt(np.mean(mixture[noise_only].astype(np.float64) ** 2))
        out_rms = np.sqrt(np.mean(cleaned[noise_only] ** 2))
        in_speech_rms = np.sqrt(np.mean(mixture[speech_region].astype(np.float64) ** 2))
        out_speech_rms = np.sqrt(np.mean(cleaned[speech_region] ** 2))

        results.append({
            "scenario": f"white_noise_std={noise_std}",
            "noise_reduction_db": round(_db(in_rms ** 2) - _db(out_rms ** 2), 2),
            "speech_retained_frac": round(out_speech_rms / in_speech_rms, 3),
        })
    return results


def bench_echo_cancellation() -> list[dict]:
    results = []
    for step_size in (0.1, 0.5, 0.9):
        rng = np.random.default_rng(42)
        n, L = 8000, 64
        far = rng.normal(0, 1000, n)
        true_path = np.zeros(L)
        true_path[5] = 0.6
        true_path[20] = 0.3
        echo = np.convolve(far, true_path)[:n]
        near = echo + rng.normal(0, 20, n)

        aec = NLMSEchoCanceller(filter_length=L, step_size=step_size)
        out = aec.process(near.astype(np.int16), far.astype(np.int16), SR).astype(np.float64)

        tail = slice(int(n * 0.75), n)
        pre_power = np.mean(near[tail] ** 2)
        post_power = np.mean(out[tail] ** 2)
        results.append({
            "scenario": f"step_size={step_size}",
            "erle_db": round(_db(pre_power) - _db(post_power), 2),
        })
    return results


def bench_dereverberation() -> list[dict]:
    results = []
    for rt60 in (0.2, 0.4, 0.8):
        rng = np.random.default_rng(42)
        n = int(1.0 * SR)
        dry_len = int(0.3 * SR)
        t = np.arange(n) / SR
        dry = np.zeros(n)
        dry[:dry_len] = _tone(t)[:dry_len]

        rir_len = int(0.5 * SR)
        tau = 0.15 * SR
        rir = rng.normal(0, 1, rir_len) * np.exp(-np.arange(rir_len) / tau)
        rir[0] = 3.0
        wet = np.convolve(dry, rir)[:n]
        wet = np.clip(wet / np.max(np.abs(wet)) * 20000, -32768, 32767).astype(np.int16)

        dewet = SpectralDereverberator(reverb_time_s=rt60).process(wet, SR).astype(np.float64)
        tail_region = slice(int(0.5 * SR), int(0.9 * SR))
        pre_rms = np.sqrt(np.mean(wet[tail_region].astype(np.float64) ** 2))
        post_rms = np.sqrt(np.mean(dewet[tail_region] ** 2))
        results.append({
            "scenario": f"assumed_rt60={rt60}s",
            "tail_reduction_db": round(_db(pre_rms ** 2) - _db(post_rms ** 2), 2),
        })
    return results


def bench_beamforming() -> list[dict]:
    results = []
    for d_true in (3, 7, 15):
        rng = np.random.default_rng(42)
        n = 8000
        source = rng.normal(0, 1000, n)
        ch0 = source + rng.normal(0, 800, n)
        ch1_clean = np.concatenate([np.zeros(d_true), source])[:n]
        ch1 = ch1_clean + rng.normal(0, 800, n)
        multi = np.stack([ch0, ch1], axis=1).astype(np.int16)

        def snr_proxy(out, ref):
            m = min(len(out), len(ref))
            a, b = out[:m].astype(np.float64), ref[:m].astype(np.float64)
            scale = np.dot(a, b) / np.dot(b, b)
            resid = a - scale * b
            return _db(np.mean((scale * b) ** 2)) - _db(np.mean(resid ** 2))

        aligned = DelaySumBeamformer([0, d_true]).process(multi, SR)
        naive = DelaySumBeamformer([0, 0]).process(multi, SR)
        aligned_snr = snr_proxy(aligned, source)
        naive_snr = snr_proxy(naive, source)
        results.append({
            "scenario": f"delay={d_true}samples",
            "aligned_snr_db": round(aligned_snr, 2),
            "naive_snr_db": round(naive_snr, 2),
            "gain_db": round(aligned_snr - naive_snr, 2),
        })
    return results


def bench_vad_impact() -> list[dict]:
    """The one real downstream consumer of audio cleanup that exists today:
    does noise suppression reduce WebRtcVAD's known false-positive-on-tone
    behavior (documented in tests/vad/test_webrtc_vad.py)?

    Noise suppression needs more context than one 20ms VAD frame to build a
    noise-floor estimate, so each scenario generates a full 1s buffer
    directly (NOT a single frame tiled/repeated - tiling a short noise
    realization manufactures artificial 50Hz-periodic structure that real
    continuous noise never has, which was caught here during development
    because it produced an implausible result; generating the full buffer
    directly avoids that artifact). The VAD frame compared before/after is
    the buffer's last 20ms, cleaned using the preceding buffer as context.
    """
    vad = WebRtcVAD(aggressiveness=3)
    ns = SpectralSubtractionNoiseSuppressor()
    results = []

    frame_ms = 20
    frame_n = SR * frame_ms // 1000
    buf_n = SR  # 1 second of context

    def make_tone(seed):
        t = np.arange(buf_n) / SR
        return (np.sin(2 * np.pi * 440 * t) * 5000).astype(np.int16)

    def make_white_noise(seed):
        return np.random.default_rng(seed).normal(0, 500, buf_n).astype(np.int16)

    def make_silence(seed):
        return np.zeros(buf_n, dtype=np.int16)

    scenarios = {
        "loud_pure_tone": make_tone,
        "white_noise_only": make_white_noise,
        "quiet_room_silence": make_silence,
    }

    for name, gen in scenarios.items():
        buf = gen(seed=1)
        before_frame = buf[-frame_n:]
        before = vad.is_speech(before_frame, SR)

        cleaned = ns.process(buf, SR)
        after_frame = cleaned[-frame_n:]
        after = vad.is_speech(after_frame, SR)

        results.append({"scenario": name, "vad_speech_before": bool(before), "vad_speech_after": bool(after)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = {
        "noise_suppression": bench_noise_suppression(),
        "echo_cancellation": bench_echo_cancellation(),
        "dereverberation": bench_dereverberation(),
        "beamforming": bench_beamforming(),
        "vad_impact": bench_vad_impact(),
    }

    for section, rows in report.items():
        print(f"\n=== {section} ===")
        for row in rows:
            print("  " + ", ".join(f"{k}={v}" for k, v in row.items()))

    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
        print(f"\nWrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
