
"""
我现在需要从零构建Agentloop循环
1.创建信息列表
2.接入大模型信息
3.创建用户角色，大模型角色
4.把信息输入大模型
5.创建工具
6.判断工具调用条件
7.如果没有就直接让大模型回答
8.如果有就开始loop循环让大模型调用工具或许信息
9.把获取到的信息放到下一轮的message里面
10.限制最大回答轮次，和当大模型不调用工具时终止
11.输出大模型回复
"""

import re
import os 
import subprocess
from pathlib import Path
import yaml

try:
    import readline
    # 输入法优化
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override= True)

if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN",None)
    
client = Anthropic(base_url = os.getenv("ANTHROPIC_BASE_URL"))

MODEL = os.environ["MODEL_ID"]
WORKDIR = Path.cwd()
SKILLS_DIR = WORKDIR / "skills"

ENVIRONMENT_PROMPT = (
    "Windows: the bash tool runs through cmd.exe; use cmd.exe syntax, not Unix "
    "Bash or PowerShell syntax, and prefer dedicated file tools for file operations"
    if os.name == "nt"
    else "Unix-like: the bash tool runs the system shell"
)

class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    @staticmethod
    def parse_frontmatter(text: str) -> tuple[dict, str]:
        lines = text.splitlines(keepends=True)
        if not lines or lines[0].rstrip("\r\n") != "---":
            return {}, text

        closing_index = next(
            (index for index, line in enumerate(lines[1:], start=1)
             if line.rstrip("\r\n") == "---"),
            None,
        )
        if closing_index is None:
            return {}, text

        frontmatter = "".join(lines[1:closing_index])
        body = "".join(lines[closing_index + 1:]).strip()
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError:
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        return metadata, body

    def scan(self):
        self.skills.clear()
        if not self.skills_dir.exists():
            return

        skills_root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            if (not manifest.is_file()
                    or not manifest.resolve().is_relative_to(skills_root)):
                continue
            content = manifest.read_text(encoding="utf-8")
            metadata, body = self.parse_frontmatter(content)
            raw_name = metadata.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
            name = name or manifest.parent.name
            raw_description = metadata.get("description")
            description = (raw_description.strip()
                           if isinstance(raw_description, str) else "")
            description = description or body.split("\n", 1)[0]
            description = " ".join(str(description).lstrip("# ").split())
            self.skills[name] = {
                "name": name,
                "description": description,
                "content": content,
            }

    def catalog(self) -> str:
        if not self.skills:
            return "(no skills found)"
        return "\n".join(
            f"- {skill['name']}: {skill['description']}"
            for skill in self.skills.values()
        )

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill:
            return skill["content"]
        available = ", ".join(self.skills) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"


SKILL_LOADER = SkillLoader(SKILLS_DIR)


def build_system_prompt() -> str:
    return (
        f"You are a coding agent at {WORKDIR}. Environment: {ENVIRONMENT_PROMPT}. "
        "Use tools to solve tasks. "
        "Act, don't explain.\n\n"
        f"Skills available:\n{SKILL_LOADER.catalog()}\n\n"
        "Use load_skill to read the full instructions when a skill applies."
    )


SYSTEM = build_system_prompt()

SUB_SYSTEM = (
    f"You are a coding agent at {WORKDIR}. Environment: {ENVIRONMENT_PROMPT}. "
    "Complete the given task, then return a concise final answer."
)

# TOOLS = [
#     {
#         "name":"bash",
#         "description": "Run a shell command",
#         "input_schema":{
#             "type":"object",
#             "properties":{
#                 "command":{
#                     "type":"string"
#                 }
#             },
#             "required":["command"]
#         }
#     }
# ]
# s02新增工具定义的schema,声明对应工具执行类型
# base_tools 给subagent做工具隔离
def run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=WORKDIR,
            capture_output=True, text=True, errors="replace", timeout=120,
        )
        output = (result.stdout + result.stderr).strip()
        return output[:50000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = (WORKDIR / path).resolve().read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = (WORKDIR / path).resolve()
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"


def run_glob(pattern: str) -> str:
    import glob
    try:
        matches = sorted({
            match for match in glob.glob(
                pattern, root_dir=WORKDIR, recursive=True)
            if (WORKDIR / match).resolve().is_relative_to(WORKDIR)
        })
        shown = matches[:200]
        if len(matches) > 200:
            shown.append("... (more matches omitted; narrow the pattern)")
        return "\n".join(shown) if shown else "(no matches)"
    except Exception as e:
        return f"Error: {e}"


BASE_TOOLS = [
    {"name": "bash", "description": "Run a shell command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file contents.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write content to a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Replace exact text in a file once.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "glob", "description": "Find files matching a glob pattern; ** matches recursively.",
     "input_schema": {"type": "object", "properties": {"pattern": {"type": "string"}}, "required": ["pattern"]}},
]

BASE_HANDLERS = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}


    # s02新增工具说明
def run_todo_write(todos: list | str) -> str:
    try:
        output = TODO.update(todos)
    except ValueError as e:
        return f"Error: {e}"
    print(f"\n\033[33m## Current Tasks\033[0m\n{output}")
    return output


SUB_TOOLS = list(BASE_TOOLS)
SUB_HANDLERS = dict(BASE_HANDLERS)


def extract_text(content) -> str:
    if not isinstance(content, list):
        return str(content)
    return "\n".join(
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    )

# 创建subagent工具
#单独隔离消息列表
#单独隔离工具
#设置最大轮次
#将消息append tool_result

def run_subagent(prompt: str) -> str:
    print("\n\033[35m[Subagent started]\033[0m")
    messages = [{"role": "user", "content": prompt}]

    for _ in range(30):
        response = client.messages.create(
            model=MODEL,
            system=SUB_SYSTEM,
            messages=messages,
            tools=SUB_TOOLS,
            max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_calls = [
            block for block in response.content if block.type == "tool_use"
        ]
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            print("\033[35m[Subagent done]\033[0m")
            return extract_text(response.content) or "(no summary)"

        results = []
        for block in tool_calls:
            output = execute_tool(block, SUB_HANDLERS)
            print(f"  \033[90m[sub] {block.name}: {output[:100]}\033[0m")
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "is_error": output.startswith(("Error:", "Unknown:", "Permission denied")),
                "content": output,
            })
        messages.append({"role": "user", "content": results})

    print("\033[35m[Subagent stopped]\033[0m")
    return "Subagent stopped after 30 turns without a final answer."



TASK_TOOL = {
    "name": "task",
    "description": "Run a subagent with fresh conversation context and return its final text.",
    "input_schema": {
        "type": "object",
        "properties": {"prompt": {"type": "string", "minLength": 1}},
        "required": ["prompt"],
    },
}

TOOLS = [*BASE_TOOLS, TASK_TOOL,
    {"name": "load_skill", "description": "Load the full SKILL.md content by skill name.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}},
]
TOOL_HANDLERS = {**BASE_HANDLERS, "task": run_subagent, "load_skill": SKILL_LOADER.load}


# 新增工具查表的内容可以结合大模型的输出进行工具查表调用对应的函数，减少大模型输出错误的风险，使用Schema约束大模型调用工具输出的参数
# 新增hook，将前后处理从agent_loop中抽离出来也就是说之前的loop是定时做任务的做定期检查现在单独抽离出来做成注册表更加可控
HOOKS = {"UserPromptSubmit": [], "PreToolUse": [], "PostToolUse": [], "Stop": []}

def register_hook(event: str, callback):
    HOOKS[event].append(callback)

def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:  # A hook result blocks this tool call.
            return result
    return None
# 权限控制
# 1.做强制不执行列表如rerf
DENY_LIST = ["rm -rf /", "sudo", "shutdown", "reboot", "mkfs", "dd if=", "> /dev/sda"]
DESTRUCTIVE = ["rm ", "> /etc/", "chmod 777"]

def check_deny_list(command: str) -> str | None:
    for pattern in DENY_LIST:
        if pattern in command:
            return f"Blocked: '{pattern}' is on the deny list"
    return None


# 2.做规则匹配检查输出命令中指定的工具和检查条件为后续问用户内容做解释
DESTRUCTIVE_COMMAND_WORD = re.compile(
    r"(?i)(?:^|[;&|()\n])\s*(?:rm|del)(?=\s|$|[;&|()])"
)


def contains_destructive_command(command: str) -> bool:
    return bool(DESTRUCTIVE_COMMAND_WORD.search(command))


PERMISSION_RULES = [
    {"tools": ["read_file", "write_file", "edit_file"],
     "check": lambda args: not (WORKDIR / args.get("path", "")).resolve().is_relative_to(WORKDIR),
     "message": "Writing outside workspace"},
    {"tools": ["bash"],
     "check": lambda args: contains_destructive_command(args.get("command", "")) or
     any(kw in args.get("command", "") for kw in ["rm ", "> /etc/", "chmod 777"]),
     "message": "Potentially destructive command"},
]

def check_rules(tool_name: str, args: dict) -> str | None:
    for rule in PERMISSION_RULES:
        if tool_name in rule["tools"] and rule["check"](args):
            return rule["message"]
    return None


# 3.询问用户批准对应的权限，暂停输出
def ask_user(tool_name: str, args: dict, reason: str) -> str:
    print(f"\n\033[33m[permission] {reason}\033[0m")
    print(f"   Tool: {tool_name}({args})")
    choice = input("   Allow? [y/N] ").strip().lower()
    return "allow" if choice in ("y", "yes") else "deny"


# 组装三道闸门
def check_permission(block) -> bool:
    if block.name == "bash":
        reason = check_deny_list(block.input.get("command", ""))
        if reason:
            print(f"\n\033[31m[blocked] {reason}\033[0m")
            return False
    reason = check_rules(block.name, block.input)
    if reason:
        decision = ask_user(block.name, block.input, reason)
        if decision == "deny":
            return False
    return True


def permission_hook(block):
    """PreToolUse: s03 check_permission() logic moved here."""
    if block.name == "bash":
        command = block.input.get("command", "")
        for pattern in DENY_LIST:
            if pattern in command:
                print(f"\n\033[31m[blocked] '{pattern}'\033[0m")
                return "Permission denied by deny list"
        if contains_destructive_command(command) or any(
            kw in command for kw in DESTRUCTIVE
        ):
            print(f"\n\033[33m[permission] Potentially destructive command\033[0m")
            print(f"   Tool: {block.name}({block.input})")
            choice = input("   Allow? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    if block.name in ("read_file", "write_file", "edit_file"):
        path = block.input.get("path", "")
        if not (WORKDIR / path).resolve().is_relative_to(WORKDIR):
            print(f"\n\033[33m[permission] Access outside workspace\033[0m")
            print(f"   Tool: {block.name}({block.input})")
            choice = input("   Allow? [y/N] ").strip().lower()
            if choice not in ("y", "yes"):
                return "Permission denied by user"
    return None

def log_hook(block):
    """PreToolUse: log every tool call."""
    args_preview = str(list(block.input.values())[:2])[:60]
    print(f"\033[90m[HOOK] {block.name}({args_preview})\033[0m")
    return None

def large_output_hook(block, output):
    """PostToolUse: warn on large output."""
    if len(str(output)) > 100000:
        print(f"\033[33m[HOOK] Large output from {block.name}: {len(str(output))} chars\033[0m")
    return None

# 打印用户输入的消息
def context_inject_hook(query: str):
    print(f"\033[90m[HOOK] UserPromptSubmit: working in {WORKDIR}\033[0m")
    return None

# 会话结束时总结
def summary_hook(messages: list):
    tool_count = sum(1 for m in messages
                     for b in (m.get("content") if isinstance(m.get("content"), list) else [])
                     if isinstance(b, dict) and b.get("type") == "tool_result")
    print(f"\033[90m[HOOK] Stop: session used {tool_count} tool calls\033[0m")
    return None

register_hook("UserPromptSubmit", context_inject_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


def execute_tool(block, handlers: dict) -> str:
    try:
        blocked = trigger_hooks("PreToolUse", block)
        if blocked is not None:
            return str(blocked)
        handler = handlers.get(block.name)
        output = handler(**block.input) if handler else f"Unknown: {block.name}"
    except TypeError as e:
        output = f"Error: Invalid arguments for {block.name}: {e}. Follow the tool input_schema and provide all required fields."
    trigger_hooks("PostToolUse", block, output)
    return str(output)


def agent_loop(messages:list):
    while True :
        response = client.messages.create(
            model = MODEL,
            system = SYSTEM,
            messages = messages,
            tools = TOOLS,
            max_tokens = 8000,
        )
        
        messages.append(
            {
                "role":"assistant",
                "content":response.content
            }
        )
        
        tool_calls = []
        
        for block in response.content:
            if block.type == "tool_use":
                tool_calls.append(block)
                
        
        if not tool_calls:
            force = trigger_hooks("Stop", messages)
            if force:
                messages.append({"role": "user", "content": force})
                continue
            return 
        
        results = []
        
        for block in tool_calls:
             print(f"\033[33m> {block.name}\033[0m")
             handler = TOOL_HANDLERS.get(block.name)
             try:
                 blocked = trigger_hooks("PreToolUse", block)
                 if blocked is not None:
                     results.append({"type": "tool_result", "tool_use_id": block.id,
                                     "is_error": True, "content": str(blocked)})
                     continue
                 output = handler(**block.input) if handler else f"Unknown: {block.name}"
             except TypeError as e:
                 output = f"Error: Invalid arguments for {block.name}: {e}. Follow the tool input_schema and provide all required fields."
             trigger_hooks("PostToolUse", block, output)
             print(output[:200])
             results.append({
                 "type":"tool_result",
                "tool_use_id" :block.id,
                "is_error": output.startswith(("Error:", "Unknown:")),
                "content":output 
             })

        messages.append({"role": "user", "content": results})
        

# 上下文压缩：
# 上下文溢出很大的原因是由于工具调用占比过高，tool_result使用次数较多
# 首先需要解决工具调用占用上下文的问题
# 1.将工具结果输出的内容做判断，当输出的内容大于50000个字符的时候将其变成大文件，存储，暴露给大模型desprtions
# 2.对于重复的调用的工具，只保留最近调用的结果作为更新
# 3.删除上下文的中间部分，保留早期记忆和近期结果
# 4.旧命令可以重新执行
# 当上下文执行完之后还是超出了，就使用大模型进行压缩，将过去的历史记录保存
# 因为大模型的输入token不完全等于程序输入的字符数量所以会有

if __name__ == "__main__":
    print("s01: Agent Loop")
    print("Enter a question, press Enter to send. Type q to quit.\n")

    history = []
    while True:
        try:
            
            query = input("\033[36ms01 >> \033[0m" if os.name == "nt"
                          else "\001\033[36m\002s01 >> \001\033[0m\002")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        trigger_hooks("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history)
        
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if getattr(block, "type", None) == "text":
                    print(block.text)
        print()
   
