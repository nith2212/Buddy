# Buddy's eval and grading kit. See testing/README.md.
# The evals import the backend's code (brain, main), so the backend folder goes on the import path.
import sys
from pathlib import Path

_BACKEND = str(Path(__file__).resolve().parent.parent / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
