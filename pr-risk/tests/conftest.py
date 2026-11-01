import sys
from pathlib import Path

# The same import paths the Action uses (see pr_risk.py): its own folder plus backend/ and workers/.
HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE.parent / "backend"), str(HERE.parent / "workers")]
