"""Delete graphics run folders older than config "keep_hours" (default 48) from output/.
Run by cleanup_output.bat (scheduled hourly by install_cleanup_task.bat). Never touches output/latest_rickywx."""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from run import clean_old_runs  # noqa: E402

if __name__ == "__main__":
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    n = clean_old_runs(cfg, datetime.now())
    print(f"{datetime.now():%Y-%m-%d %H:%M}  cleanup: removed {n} folder(s) older than {cfg.get('keep_hours', 48)} h")
