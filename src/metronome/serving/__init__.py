"""Non-stop serving: registry, ONNX Runtime engine, atomic hot swap, residual monitor, replay.

This package must stay importable without PyTorch: the serving image installs only the core
dependencies. Anything that trains lives in `metronome.serving.worker` and imports torch lazily.
"""
