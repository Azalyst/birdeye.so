import os
import sys
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import execute_tool, TOOLS

NIM_API_KEY = os.environ.get("NIM_API_KEY")
PRIMARY_MODEL = "deepseek-ai/deepseek-v4-pro"
FALLBACK_MODEL = "qwen/qwen2.5-coder-32b-instruct"
BASE_URL = "https://integrate.api.nvidia.com/v1"

client = OpenAI(api_key=NIM_API_KEY, base_url=BASE_URL)


def get_system_prompt():
    for path in ["AGENTS.md", "../AGENTS.md"]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            continue
    return "You are an AI assistant with access to tools."


def extract_output_path(task: str, default: str = "agent_output.txt") -> str:
    if "save results to " in task.lower():
        try:
            parts = task.lower().split("save results to ")
            if len(parts) > 1:
                path = parts[1].split(" ")[0].strip()
                if path:
                    return path
        except Exception:
            pass
    return default


def save_output(path: str, content: str):
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Output saved to {path}")
    except Exception as e:
        print(f"Error saving to {path}: {e}")
        with open("agent_output.txt", "w", encoding="utf-8") as f:
            f.write(content)


def parse_tool_call(content: str):
    """Extract tool name and args. Returns (tool_name, args) or (None, None)."""
    start_marker = "```tool_call"
    end_marker = "```"
    if start_marker not in content:
        return None, None
    try:
        part = content.split(start_marker)[1].split(end_marker)[0].strip()
        tool_data = json.loads(part)
        return tool_data.get("tool"), tool_data.get("args", {})
    except Exception as e:
        print(f"Tool parse error: {e}")
        return None, None


def run_agent(task: str) -> str:
    print(f"Task: {task}")
    system_prompt = get_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    max_iterations = 15

    for i in range(max_iterations):
        print(f"\n--- Iteration {i + 1} ---")

        # Try Primary, then Fallback
        content = None
        for model in [PRIMARY_MODEL, FALLBACK_MODEL]:
            try:
                print(f"  Requesting {model}...")
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                )
                content = response.choices[0].message.content
                break
            except Exception as e:
                print(f"  Error with {model}: {e}")
                if model == FALLBACK_MODEL:
                    return f"Agent failed on both models. Last error: {e}"
                print("  Retrying with fallback...")

        if content is None:
            return "Agent failed to generate content."
        messages.append({"role": "assistant", "content": content})
        print(f"Agent: {content[:500]}...")

        # ── PRIORITY 1: execute tool call if present ──────────────────────
        tool_name, args = parse_tool_call(content)
        if tool_name:
            print(f"Executing tool: {tool_name}  args: {args}")
            try:
                observation = execute_tool(tool_name, args)
            except Exception as e:
                observation = f"Tool execution error: {e}"
            print(f"Observation: {str(observation)[:500]}...")
            messages.append({"role": "user", "content": f"Observation: {observation}"})
            continue  # go back to top — check for next tool call or final answer

        # ── PRIORITY 2: final answer ──────────────────────────────────────
        if "Final Answer:" in content:
            output_path = extract_output_path(task)
            save_output(output_path, content)
            return content

        # ── Neither tool call nor final answer ────────────────────────────
        if i >= 4:
            msg = f"Agent produced no tool call or final answer after {i + 1} iterations. Aborting."
            print(msg)
            return msg

    return "Max iterations reached without a final answer."


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else "list files in current directory"
    run_agent(task)
