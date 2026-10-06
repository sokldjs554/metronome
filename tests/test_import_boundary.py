from __future__ import annotations

import subprocess
import sys


def test_serving_package_never_imports_torch() -> None:
    """The serving image installs only the core dependencies; importing the service must not pull torch."""
    code = (
        "import sys; import metronome.serving.app, metronome.serving.worker, metronome.cli; "
        "bad = sorted(m for m in sys.modules if m.split('.')[0] in {'torch', 'polars', 'pandas', 'mlflow', 'pyspark'}); "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
