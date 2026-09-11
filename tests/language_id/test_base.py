from core.asr.base import LanguageDetectionResult
from core.language_id.base import LOW_CONFIDENCE_THRESHOLD, LanguageIdentifier


class _FixedIdentifier(LanguageIdentifier):
    def __init__(self, result: LanguageDetectionResult):
        self._result = result

    def identify(self, audio, sample_rate_hz):
        return self._result


def test_high_confidence_is_confident():
    identifier = _FixedIdentifier(LanguageDetectionResult(language="es", confidence=0.9))
    result = identifier.identify(None, 16000)
    assert identifier.is_confident(result) is True


def test_low_confidence_is_not_confident():
    identifier = _FixedIdentifier(LanguageDetectionResult(language="es", confidence=0.1))
    result = identifier.identify(None, 16000)
    assert identifier.is_confident(result) is False


def test_boundary_confidence_is_confident():
    identifier = _FixedIdentifier(
        LanguageDetectionResult(language="es", confidence=LOW_CONFIDENCE_THRESHOLD)
    )
    result = identifier.identify(None, 16000)
    assert identifier.is_confident(result) is True
