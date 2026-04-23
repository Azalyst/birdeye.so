"""
Back-compat shim. Canonical tools live at repo root (`tools.py`).
Loads the root module by absolute path to avoid sys.path collisions.
"""
import importlib.util as _ilu
import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_spec = _ilu.spec_from_file_location("_root_tools", _os.path.join(_ROOT, "tools.py"))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

execute_tool = _mod.execute_tool
TOOLS = _mod.TOOLS
