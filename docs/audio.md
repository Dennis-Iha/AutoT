# AT-CORE Audio Subsystem

This is the reference for AT-CORE's audio I/O and signal-processing layer:
how audio actually moves from a microphone (or a WAV file) through buffers,
voice-activity detection, and the DSP building blocks, down to individual
line-level behavior. `docs/ai.md` covers the same code from the ML-pipeline
side (what stage feeds what model, LID/ASR/translation/TTS); this document
is the engineering layer underneath that: threading, buffer contracts,
sample formats, and the parts of Phase 1-3 that were verified against real
hardware versus only against synthetic signals.

Scope: `core/audio/{capture,ring_buffer,wav_io,diagnostics,playback}.py`,
`core/vad/{base,webrtc_vad,segmenter}.py`, `core/denoise/stft.py`, and
`core/beamforming/{base,delay_sum}.py`. The other three `core/denoise/*.py`
algorithm modules (noise suppression, echo cancellation, dereverberation)
are covered in `docs/ai.md`'s Stage 2 table — they consume `stft.py` but
their algorithms aren't re-described here.

## Data format and threading contract

Every module in this layer agrees on one representation: mono, 16kHz,
int16 PCM, shape `(n,)` or `(n, channels)`. Nothing here does resampling or
format negotiation — `AudioPlayback.play()` lets PortAudio/the OS handle
rate conversion if a device's native rate differs, but capture and the VAD
path both assume the configured rate is already correct.

There are exactly two threads in this layer: PortAudio's own callback
thread (real-time, must never block) and whatever thread the caller reads
from. `MicrophoneCapture._callback` runs on the first; `AudioRingBuffer` is
the one object designed to be safely written from one and read from the
other (a `threading.Lock` around each operation). Phase 9's real
concurrency bug (documented in `docs/roadmap.md`) was a violation of this
exact contract: an early version of `tools/at_translate.py` called the
full translation pipeline directly from `on_frames`, which runs on the
PortAudio callback thread — since a segment can take 17-90+ seconds to
process, this blocked audio capture for the entire duration. The fix
(`core/streaming/session.py`) lives outside this layer's files, but the
constraint it exists to enforce — nothing slow ever runs on the capture
callback — is this layer's responsibility to uphold.

## Capture: `core/audio/capture.py`

`MicrophoneCapture` wraps a `sounddevice.InputStream` (PortAudio). Its
callback does four things per block, in order: record inter-callback
timing and stream-status flags into `AudioDiagnostics`, convert the
incoming `float32` block to `int16` (`indata * 32767.0`), write it into the
`AudioRingBuffer`, and — only if the caller supplied one — invoke
`on_frames(pcm)`. `on_frames` is the hook `SpeechSegmenter` or a streaming
session attaches to; per the threading contract above, whatever it does
must be non-blocking.

Configurable at construction: `sample_rate_hz` (default 16000),
`channels` (default 1), `blocksize_samples` (default 320, i.e. 20ms at
16kHz — matches the VAD frame size below so no re-framing is needed
downstream), and `ring_buffer_seconds` (default 10s of backing capacity).
`start()`/`stop()` and the context-manager form (`__enter__`/`__exit__`)
open and close the PortAudio stream; calling `start()` twice raises
`RuntimeError` rather than silently reopening.

## Ring buffer: `core/audio/ring_buffer.py`

`AudioRingBuffer` is a fixed-capacity circular buffer of int16 PCM,
`(capacity_samples, channels)` preallocated at construction — no
per-block allocation on the hot path. `write()` never blocks and never
raises on overflow: if the incoming block is larger than the whole
buffer, only the most recent `capacity_samples` are kept; if the buffer is
already full, the oldest unread samples are silently overwritten. Both
cases increment `dropped_samples`, a plain counter the diagnostics layer
can surface — overflow is a real, measurable event, not a hidden one.
`read_available()` drains oldest-first, handling the wraparound case
(the requested range crosses the end of the backing array) by
concatenating the two segments. `available_samples` reports how much
unread audio is currently buffered.

## WAV I/O: `core/audio/wav_io.py`

A two-function wrapper around `soundfile` (libsndfile): `write_wav` always
writes `PCM_16` and creates the parent directory if needed; `read_wav`
reads back int16 samples and the file's sample rate. Used in three places:
`tools/mic_vad_demo.py` writing detected speech segments to disk for manual
inspection, diagnostic captures generally, and every test fixture WAV in
`tests/fixtures/`. Nothing here does resampling or format conversion — a
file at the wrong rate is read as-is.

## Diagnostics: `core/audio/diagnostics.py`

Phase 1's spec required measuring input latency, buffer latency, CPU, and
memory usage rather than assuming the audio path is healthy, and this
module is where those numbers actually get collected — one place shared by
`tools/mic_vad_demo.py` and later benchmark scripts, not reinvented per
tool. `AudioDiagnostics` wraps a `core.common.metrics.Metrics` instance
(namespace `"audio"`) and tracks: `frames_captured` (running total),
`inter_callback_ms` (a timer — large deviations from the configured
blocksize duration indicate scheduling jitter or under/overrun risk), and
`stream_status_events` (raw PortAudio status strings, e.g. underflow
flags). `resource_usage()` reads `psutil.Process.cpu_percent()` and
`memory_info().rss` for the current process, and `snapshot()` returns all
of the above as one dict — the shape every diagnostic/benchmark tool in
this layer emits.

## Playback: `core/audio/playback.py`

`AudioPlayback` is capture's mirror: `sd.play()`/`sd.wait()` instead of an
input stream. `play()` accepts either int16 (converted to float32 by
dividing by 32768.0) or float audio, passed through unchanged; `blocking`
(default `True`) determines whether it waits for playback to finish before
returning. This module didn't exist before Phase 8 — Phase 1-7 only needed
capture — and was added specifically so `tools/at_translate.py` could speak
TTS output back through a real device instead of only writing WAV files.

## Voice activity detection: `core/vad/webrtc_vad.py`

`WebRtcVAD` implements the `VADEngine` ABC (`core/vad/base.py`), which is
deliberately narrow: classify one fixed-size frame as speech or not, with
all temporal logic (onset/offset debouncing, hangover) left to the
segmenter below — so a different VAD backend could be swapped in without
touching segmentation logic. It wraps `webrtcvad` (Google's WebRTC VAD C
extension): no model file, sub-millisecond per 20ms frame, aggressiveness
0-3. `is_speech()` validates strictly before calling into the C extension —
wrong sample rate, wrong dtype, non-mono input, or a frame length that
doesn't correspond to exactly 10/20/30ms at the given rate all raise
`ValueError` rather than guessing at what the caller meant.

**Known, documented limitation — not fixed, not hidden**:
`tests/vad/test_webrtc_vad.py::test_loud_pure_tone_is_misclassified_as_speech`
shows that a loud 440Hz pure sine tone (amplitude 5000 on an int16 scale)
is classified as speech even at `aggressiveness=3`, WebRTC VAD's strictest
setting — this is not real speech, and the test's own comment states the
finding plainly: webrtcvad's energy/sub-band features key on strong
periodic energy in the speech frequency range, so any strongly tonal
signal in that range can trigger it. The companion test,
`test_quiet_pure_tone_is_not_speech`, confirms this is specifically an
energy-threshold effect and not `is_speech()` being unconditionally true:
the same 440Hz tone at amplitude 50 is correctly rejected. This is tracked
as a real accuracy limitation of the VAD backend itself, kept honest in
the test suite as a concrete regression case, rather than papered over.

`tools/audio_cleanup_benchmark.py` was written in part to check whether
Phase 3's noise suppression closes this gap, and the roadmap's Phase 3
results record a real negative result: spectral-subtraction noise
suppression as currently tuned does **not** fix WebRtcVAD's
false-positive behavior on broadband noise, and pushing its
over-subtraction factor higher to try to defeat that case would trade away
real speech retention — the wrong tradeoff. The roadmap's stated
follow-up is to revisit VAD noise-robustness with either a better VAD
(e.g. a neural VAD) or the segmenter's own onset-ratio hysteresis, not by
over-suppressing.

## Segmentation: `core/vad/segmenter.py`

`SpeechSegmenter` turns the frame-level VAD stream into discrete
`SpeechSegment`s using a sliding-window "ratio of voiced frames" collector
— the same pattern the reference `webrtcvad` examples use. Two rings of
recent `(frame, is_speech)` state are involved: an onset ring
(`onset_window_frames`, derived from `min_speech_ms`, default 200ms → 10
frames at 20ms/frame) and, once triggered, an offset ring
(`offset_window_frames`, from `hangover_ms`, default 300ms → 15 frames). A
segment starts once more than `ONSET_RATIO` (0.9) of the onset ring is
voiced — and is seeded with that entire window's audio, so the speech that
triggered detection isn't lost. It ends once more than `OFFSET_RATIO`
(0.9) of the offset ring is silent, or once the segment has run for
`max_segment_ms` (default 20000ms), which force-closes it
(`forced_close=True` on the returned `SpeechSegment`) so a streaming
pipeline never buffers unboundedly waiting for silence that isn't coming.
`flush()` force-closes an in-progress segment on stream stop; `reset()`
clears both rings and the underlying VAD's state.

## STFT/ISTFT: `core/denoise/stft.py`

The shared spectral-domain primitive used by noise suppression and
dereverberation (both described in `docs/ai.md`). `stft()` computes a
centered short-time Fourier transform of a 1-D real signal using a
**periodic** (DFT-even) Hann window — explicitly not numpy's default
symmetric `np.hanning()`, which is the wrong variant for STFT/ISTFT
round-tripping. The signal is zero-padded by `frame_size // 2` on each
side before framing (the standard "centered" convention), and any
additional padding needed to reach a whole number of hop-aligned frames is
added at the end. `istft()` reverses this with weighted overlap-add
(WOLA): apply the same analysis window at synthesis time, accumulate, and
normalize by the accumulated sum of squared windows (floored at `1e-8` to
avoid a divide-by-zero at the edges) — this gives exact reconstruction
wherever frames overlap enough to keep that sum bounded away from zero,
true in the interior for a Hann window with `hop_size <= frame_size / 2`
(the default `frame_size=512, hop_size=256` satisfies this exactly).

`tests/denoise/test_stft.py` verifies this round-trips correctly across
five signal lengths (800, 4000, 16000, 16001, 8123 samples — including
lengths that don't divide evenly into whole frames). The test's own
comment states the measured result plainly: max absolute reconstruction
error is **~1e-15** (machine precision for `float64`), with the test's
actual assertion tolerance (`atol=1e-9`) set as a generous margin below
that measured number rather than tuned to just barely pass.

This is a block/offline transform — arbitrary-length buffer in, same
length buffer out — suitable for cleaning a whole captured segment at
once, which is how Phase 3 uses it today. A frame-synchronous causal
streaming variant is explicitly deferred (documented in the module's own
docstring) until the rest of the pipeline needs one.

## Beamforming: `core/beamforming/delay_sum.py`

`DelaySumBeamformer` implements the `Beamformer` ABC (`core/beamforming/
base.py`): combine a multi-channel buffer `(n_samples, n_channels)` into
one enhanced mono channel. This is delay-and-sum, the simplest real
spatial filter and the standard first step before techniques like MVDR or
a GSC that need per-deployment calibration data this project doesn't have
without real hardware. Given a list of per-channel sample delays, each
channel is shifted (`_shift`, zero-filling the exposed edge) to
time-align it to a reference, then the aligned channels are averaged —
coherent averaging boosts SNR for a source arriving from the steered
direction while incoherent per-channel noise partially cancels. Output is
cast back to the input dtype, with integer types clipped/rounded to the
dtype's range rather than silently overflowing.

`estimate_delay_samples()` is a separate, plain building block: it
estimates the integer-sample delay between two channels via
cross-correlation peak search over a bounded lag window. The module's own
docstring is explicit that this is not full GCC-PHAT (which additionally
whitens the cross-spectrum before the peak search) — a simpler technique
was enough to validate the beamformer's math against synthetic
ground-truth delays.

`core/beamforming/base.py`'s own docstring states the target hardware
context: AT's earbud design calls for 2-4 MEMS microphones per earbud
specifically to enable this (consistent with `hardware/
AT-H1-headphone-prototype.md`'s mic-array spec) — but no real multi-mic
hardware exists yet, so beamforming here is validated entirely with
synthetic multi-channel signals, honestly scoped as not yet proven to
transfer to a real array's geometry, coupling, or self-noise.

## Hardware-validated vs. synthetic-only

Not every module in this layer has been checked against the same kind of
ground truth. Per `docs/roadmap.md`'s Phase 1/3 results and the modules
read for this document:

| Component | Validated against |
|---|---|
| Microphone capture (`capture.py`) | Real hardware — manual smoke test via `tools/mic_vad_demo.py` (opens a real PortAudio input device; not an automated pytest, since CI shouldn't require a live mic) |
| Playback (`playback.py`) | Real hardware — manually verified per `tests/audio/test_playback.py`'s own docstring; its automated tests mock `sounddevice` deliberately, so CI doesn't play audio out loud on every run |
| Ring buffer, WAV I/O, diagnostics | Automated unit tests only (no real-hardware dependency to validate against — these are pure data-structure/format logic) |
| VAD (`webrtc_vad.py`) + segmenter | Automated unit tests with synthetic tones/silence, plus the real-hardware smoke test above (`mic_vad_demo.py` runs live VAD+segmentation over a real mic) |
| STFT/ISTFT (`stft.py`) | Synthetic signals only (random Gaussian noise, for round-trip accuracy) — no speech-specific claim is made here, correctly, since it's a pure transform |
| Noise suppression, echo cancellation, dereverberation, beamforming | **Synthetic signals only** — known ground-truth noise/echo/reverb/multi-channel signals built for `tools/audio_cleanup_benchmark.py`. No real multi-mic array or real acoustic recordings exist in this environment. See `docs/ai.md` Stage 2 for the measured numbers (~6dB noise-floor reduction, ~29dB ERLE, ~10dB reverberant-tail reduction, ~8.5dB beamforming SNR gain) |

## Status

Per this project's readiness framework (prototype / engineering prototype
/ production candidate / production ready — see
`docs/commercial-product-architecture.md`):

- **Capture, ring buffer, WAV I/O, diagnostics, playback**: engineering
  prototype. Real, tested code, with capture and playback additionally
  smoke-tested on real hardware — but neither has been exercised under
  sustained/production load (long-running sessions, device hot-plug,
  underrun recovery beyond what a flag records).
- **VAD & segmentation**: engineering prototype. Real, tested, including
  the documented pure-tone false-positive limitation above; verified live
  on real hardware for capture+VAD+segmentation together via
  `tools/mic_vad_demo.py`.
- **STFT/ISTFT, denoise, beamforming**: engineering prototype. Real,
  tested code and real synthetic measurements, but none of it is wired
  into `TranslationPipeline.process()`'s live chain today (per
  `docs/ai.md` Stage 2), and none of it has been validated against real
  acoustic conditions or real multi-mic hardware.
