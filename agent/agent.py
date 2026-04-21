import os
import sys
import json
import time
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path for tools import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import execute_tool, TOOLS

# Configuration
NIM_API_KEY = os.environ.get("NIM_API_KEY")
MODEL = "qwen/qwen2.5-coder-32b-instruct"
BASE_URL = "https://integrate.api.nvidia.com/v1"

client = OpenAI(api_key=NIM_API_KEY, base_url=BASE_URL)

def get_system_prompt():
    try:
        with open("AGENTS.md", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "You are an AI assistant with access to tools."

def run_agent(task):
    print(f"Task: {task}")
    
    system_prompt = get_system_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task}
    ]
    
    max_iterations = 15
    for i in range(max_iterations):
        print(f"\n--- Iteration {i+1} ---")
        
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0.1
        )
        
        content = response.choices[0].message.content
        messages.append({"role": "assistant", "content": content})
        
        print(f"Agent: {content}")
        
        if "Final Answer:" in content:
            # Write output to file for GitHub Action to pick up
            with open("agent_output.txt", "w", encoding="utf-8") as f:
                f.write(content)
            return content
        
        # Look for tool calls in the content
        # Format expected: ```tool_call {"tool": "...", "args": {...}} ```
        if "tool_call" in content:
            try:
                # Extract JSON from the content
                start_marker = "```tool_call"
                end_marker = "```"
                
                if start_marker in content:
                    part = content.split(start_marker)[1].split(end_marker)[0].strip()
                    tool_data = json.loads(part)
                    
                    tool_name = tool_data.get("tool")
                    args = tool_data.get("args", {})
                    
                    print(f"Executing tool: {tool_name} with args: {args}")
                    observation = execute_tool(tool_name, args)
                    print(f"Observation: {observation[:200]}...")
                    
                    messages.append({"role": "user", "content": f"Observation: {observation}"})
                else:
                    # Alternative: just look for the JSON if no markers
                    # (Simplified for now)
                    pass
            except Exception as e:
                error_msg = f"Error executing tool: {e}"
                print(error_msg)
                messages.append({"role": "user", "content": f"Observation: {error_msg}"})
        else:
            # If no tool call and no final answer, the agent might be stuck or just talking
            if i > 5:
                return "Agent stuck without tool calls or final answer."

    return "Max iterations reached."

if __name__ == "__main__":
    if len(sys.argv) > 1:
        task = sys.argv[1]
    else:
        task = "list files in current directory"
    
    run_agent(task)
