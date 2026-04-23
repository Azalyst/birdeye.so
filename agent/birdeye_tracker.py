"""
Back-compat shim. Canonical multi-chain tracker lives at repo root
(`birdeye_tracker.py`). Loads the root module by absolute path to
avoid sys.path collisions.
"""
import importlib.util as _ilu
import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location("_root_birdeye_tracker", _os.path.join(_ROOT, "birdeye_tracker.py"))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("_")})
