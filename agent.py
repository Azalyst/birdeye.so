import json
import logging
import re
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import execute_tool, TOOLS

NIM_API_KEY = os.environ.get("NIM_API_KEY")
MODEL = "qwen/qwen2.5-coder-32b-instruct"
BASE_URL = "https://integrate.api.nvidia.com/v1"

log = logging.getLogger(__name__)
client = OpenAI(api_key=NIM_API_KEY, base_url=BASE_URL)

REPORTS_DIR = Path(__file__).parent / "reports"
ALLOWED_EXTS = {".md", ".json", ".txt"}
TOOL_CALL_RE = re.compile(r"<tool>\s*(\{.*?\})\s*</tool>", re.DOTALL)
ALLOWED_TOOLS = {"bash", "read_file", "write_file", "list_dir", "search"}  # based on tools.py
ALLOWED_KEYS = {"tool", "args"}


def get_system_prompt():
    for path in ["AGENTS.md", "../AGENTS.md"]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            continue
    return "You are an AI assistant with access to tools."


def safe_output_path(task: str, default: str = "agent_output.md") -> Path:
    """Extract an output path from the task, but force it under reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    m = re.search(r"save (?:results? )?to ([^\s\"']+)", task or "", re.I)
    candidate = m.group(1) if m else default
    name = os.path.basename(candidate)               # strip any directory
    if "/" in candidate or "\\" in candidate or ".." in candidate:
        name = default
    p = (REPORTS_DIR / name).resolve()
    if REPORTS_DIR.resolve() not in p.parents and p.parent != REPORTS_DIR.resolve():
        p = REPORTS_DIR / default
    if p.suffix.lower() not in ALLOWED_EXTS:
        p = p.with_suffix(".md")
    return p


def save_output(task: str, content: str) -> Path:
    p = safe_output_path(task)
    p.write_text(content, encoding="utf-8")
    print(f"Output saved to {p}")
    return p


def parse_tool_call(text: str):
    m = TOOL_CALL_RE.search(text or "")
    if not m:
        return None, None
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        raise ValueError(f"Malformed tool-call JSON: {e}")
    if not isinstance(obj, dict):
        raise ValueError("Tool call must be a JSON object")
    extra = set(obj.keys()) - ALLOWED_KEYS
    if extra:
        raise ValueError(f"Unknown keys in tool call: {extra}")
    tool = obj.get("tool")
    args = obj.get("args", {})
    if tool not in ALLOWED_TOOLS:
        raise ValueError(f"Tool {tool!r} not in allowlist")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    return tool, args


MAX_ITERATIONS = 15
MAX_HISTORY_MESSAGES = 12
MAX_TOTAL_TOKENS = 60_000  # rough cap

def _approx_tokens(messages) -> int:
    return sum(len(m.get("content", "")) for m in messages) // 4

def run_agent(task: str) -> str:
    print(f"Task: {task}")
    messages = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": task}
    ]
    
    for i in range(MAX_ITERATIONS):
        print(f"\n--- Iteration {i + 1} ---")
        
        if _approx_tokens(messages) > MAX_TOTAL_TOKENS:
            msg = f"Token budget exceeded — stopping at iteration {i}"
            print(msg)
            return msg
            
        # Keep system + last N messages
        if len(messages) > MAX_HISTORY_MESSAGES + 1:
            messages = [messages[0]] + messages[-MAX_HISTORY_MESSAGES:]
            
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.1,
            )
            content = response.choices[0].message.content
        except Exception as e:
            return f"LLM Error: {e}"

        messages.append({"role": "assistant", "content": content})
        print(f"Agent: {content[:500]}...")

        try:
            tool_name, args = parse_tool_call(content)
        except ValueError as e:
            err_msg = f"Tool parse error: {e}. Try again."
            print(err_msg)
            messages.append({"role": "user", "content": err_msg})
            continue

        if tool_name:
            print(f"Executing tool: {tool_name}")
            try:
                observation = execute_tool(tool_name, args)
            except Exception as e:
                observation = f"Tool execution error: {e}"
            print(f"Observation: {str(observation)[:500]}...")
            messages.append({"role": "user", "content": f"Observation: {observation}"})
            continue

        if "Final Answer:" in content:
            save_output(task, content)
            return content

        if i >= 10:
            return "Looping detected or no progress after 10 turns."

    return "Max iterations reached without a final answer."


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "list files in current directory"
    run_agent(task)
