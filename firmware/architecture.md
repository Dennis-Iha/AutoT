# Firmware Architecture: Embedded Audio (Phase 14) + Firmware (Phase 15)

**Status: design document, not implemented.** Both phases require writing
and testing drivers/boot code against physical hardware this environment
does not have. Writing I2S/PDM driver code or a bootloader with nothing to
run it on would produce exactly what this project's Engineering Principles
forbid: "do not create placeholder implementations for core functionality
and call them complete." What follows is the interface/architecture design
these phases would implement, once Phase 12/13's physical hardware exists.

## Phase 14: embedded audio hardware abstraction layer (design)

The goal, once real hardware is selected (`hardware/hardware-selection.md`):
give `core/audio/capture.py` and `core/audio/playback.py` a second backend
alongside the current PortAudio/sounddevice one, so the SAME
`MicrophoneCapture`/`AudioPlayback` interfaces this project already tests
(Phases 1, 8) work against embedded I2S/PDM hardware without changing any
downstream code (`core/vad`, `core/orchestration`, `tools/at_translate.py`).
This is exactly why those two classes were built as small, swappable
wrappers in the first place (see `core/audio/capture.py`'s docstring).

```
core/audio/capture.py's MicrophoneCapture
    |
    +-- PortAudio backend (sounddevice)      <- IMPLEMENTED, tested (Phase 1)
    +-- Embedded I2S/PDM backend              <- NOT IMPLEMENTED, needs real hardware
            |
        ALSA/Linux kernel I2S or PDM driver (vendor BSP-provided, e.g.
        NVIDIA's L4T audio driver stack per hardware-selection.md, or
        equivalent for whatever Phase 12 hardware is actually acquired)
```

A real embedded backend needs, in order, none of which can be built here:
1. A physical board with wired mics (Phase 13).
2. The vendor's Linux audio driver stack actually loading and exposing an
   ALSA PCM device for the mic array.
3. Only then does it make sense to write
   `core/audio/embedded_capture.py` implementing the existing interface
   against that ALSA device (likely still via a `sounddevice`/PortAudio
   ALSA backend, since PortAudio already supports arbitrary ALSA devices -
   this may turn out to need no new code at all beyond pointing
   `MicrophoneCapture(device=...)` at the right ALSA device name, which is
   already a supported parameter, untested against embedded hardware).

## Phase 15: firmware architecture (design)

```
Bootloader (vendor-provided for Phase 12 hardware, e.g. Jetson's
            pre-installed bootloader / L4T flashing tools)
    -> Secure boot (NOT designed - needs a real hardware root of trust;
                     see Phase 20 for the software-side security work that
                     IS buildable without hardware)
    -> OS (embedded Linux - Yocto or the vendor's own BSP, per Phase 12's
            OS-support findings for whichever board is acquired)
    -> Drivers (audio per Phase 14 above, Bluetooth per the companion-chip
                findings in hardware-selection.md, storage, power)
    -> Device services (watchdog, thermal protection, battery management -
                        none implemented; would be systemd units or a
                        small supervisor process on embedded Linux, not
                        exotic firmware-level code, since Phase 12's
                        candidates are all full Linux-capable SoCs, not
                        bare-metal MCUs)
    -> AI runtime (whisper.cpp + ctranslate2 + onnxruntime - ALREADY BUILT
                    and tested on the dev workstation, Phases 5-7; porting
                    means rebuilding for the target's architecture/OS, not
                    rewriting)
    -> Translation service (core/orchestration/pipeline.py + core/streaming -
                            ALREADY BUILT and tested, Phases 8-9; this is
                            the piece most likely to port with the least
                            change, since it's pure Python/subprocess glue
                            with no hardware-specific code in it today)
```

**The honest summary**: Phase 15's "firmware" for AT's Phase 12 hardware
candidates (all full embedded-Linux-capable SoCs, not bare-metal MCUs) is
mostly standard embedded Linux systems engineering (BSP bring-up, systemd
services, OTA via a package manager or A/B partition scheme) rather than
bespoke low-level firmware - which is good news for how much of Phases
5-10's software survives unchanged, but none of it can be validated without
the Phase 12 hardware this environment lacks.

## What IS buildable without hardware (see other Phase 13+ work)

Phase 16 (dual-earbud coordination) and Phase 17 (conversation mode) are
protocol/orchestration logic that can be built and tested in software today
using simulated channels standing in for a real BLE link - see
`core/coordination/` and `core/orchestration/conversation.py`. Phase 20's
software-side security (model package signing, already partially in place
via Phase 10's checksums) and Phase 21's privacy behavior are also
buildable without physical hardware.
