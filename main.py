from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

APP_DIR = Path(__file__).resolve().parent / "ai-trading-bot"
APP_MAIN = APP_DIR / "main.py"

sys.path.insert(0, str(APP_DIR))

spec = spec_from_file_location("ai_trading_bot_main", APP_MAIN)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load app module from {APP_MAIN}")

module = module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app
