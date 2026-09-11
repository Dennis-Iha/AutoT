from core.common.offline_runtime import (
    OfflineReadinessReport,
    ReadinessCheck,
    check_offline_readiness,
)


def test_report_ready_true_when_all_checks_pass():
    report = OfflineReadinessReport(checks=[
        ReadinessCheck("a", True, "ok"),
        ReadinessCheck("b", True, "ok"),
    ])
    assert report.ready is True
    assert report.issues() == []


def test_report_ready_false_when_any_check_fails():
    report = OfflineReadinessReport(checks=[
        ReadinessCheck("a", True, "ok"),
        ReadinessCheck("b", False, "missing"),
    ])
    assert report.ready is False
    assert len(report.issues()) == 1
    assert report.issues()[0].component == "b"


def test_empty_report_is_ready():
    assert OfflineReadinessReport(checks=[]).ready is True


def test_unknown_source_language_reports_failure():
    # "xx" is not in models/registry/translation_models.json - deterministic
    # regardless of which real models are installed on this machine.
    report = check_offline_readiness(languages=["xx"], target_language="en", verify_checksums=False)
    translation_checks = [c for c in report.checks if "translation" in c.component]
    assert len(translation_checks) == 1
    assert translation_checks[0].ok is False
    assert report.ready is False


def test_source_equals_target_needs_no_translation_check():
    report = check_offline_readiness(languages=["en"], target_language="en", verify_checksums=False)
    translation_checks = [c for c in report.checks if "translation" in c.component]
    assert translation_checks == []


def test_unknown_tts_voice_id_reports_failure():
    report = check_offline_readiness(
        languages=["en"], target_language="en", tts_voice_id="nonexistent-voice", verify_checksums=False
    )
    tts_checks = [c for c in report.checks if "TTS" in c.component]
    assert len(tts_checks) == 1
    assert tts_checks[0].ok is False


def test_unknown_asr_model_id_reports_failure():
    report = check_offline_readiness(
        languages=["en"], target_language="en", asr_model_id="whisper-xl", verify_checksums=False
    )
    asr_checks = [c for c in report.checks if "ASR" in c.component]
    assert len(asr_checks) == 1
    assert asr_checks[0].ok is False


def test_always_checks_whisper_cpp_binary():
    report = check_offline_readiness(languages=["en"], target_language="en", verify_checksums=False)
    binary_checks = [c for c in report.checks if "binary" in c.component]
    assert len(binary_checks) == 1


def test_verify_checksums_false_is_faster_than_true():
    import time

    languages = ["ar", "es"]
    start = time.perf_counter()
    check_offline_readiness(languages=languages, target_language="en", verify_checksums=False)
    fast_s = time.perf_counter() - start

    start = time.perf_counter()
    check_offline_readiness(languages=languages, target_language="en", verify_checksums=True)
    full_s = time.perf_counter() - start

    # Only meaningful if the underlying models are actually installed (full
    # checksum verification reads whole files); if not installed, both
    # paths are fast existence checks and this isn't a useful comparison.
    from core.translation.model_registry import TranslationModelRegistry

    registry = TranslationModelRegistry.load()
    any_installed = any(
        (entry := registry.get(lang, "en")) is not None and entry.is_ready() for lang in languages
    )
    if any_installed:
        assert full_s >= fast_s
