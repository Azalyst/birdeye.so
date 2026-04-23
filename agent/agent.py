"""
Back-compat shim. The canonical agent lives at repo root (`agent.py`).
This module re-exports its symbols so legacy imports keep working.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import importlib.util as _ilu

_spec = _ilu.spec_from_file_location("_root_agent", os.path.join(_ROOT, "agent.py"))
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

run_agent = _mod.run_agent
get_system_prompt = _mod.get_system_prompt
extract_output_path = _mod.extract_output_path
save_output = _mod.save_output
parse_tool_call = _mod.parse_tool_call

if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "list files in current directory"
    run_agent(task)
