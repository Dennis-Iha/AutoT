"""Real-time streaming session: decouples audio capture from pipeline
processing so the mic keeps listening while a previous segment is still
being translated/spoken (Phase 9). See core/streaming/session.py."""
