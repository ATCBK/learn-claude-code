
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


import os 
import subprocess

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
    
client = Anthropic(base_url = (ANTHROPIC_BASE_URL))

MOEDL = os.environ["MODEL_ID"]

ENVIRONMENT_PROMPT = (
    "Windows: the bash tool runs through cmd.exe; use cmd.exe syntax, not Unix "
    "Bash or PowerShell syntax"
    if os.name == "nt"
    else "Unix-like: the bash tool runs the system shell"
)

SYSTEM = (
    f"You are a coding agent at {os.getcwd()}. Environment: {ENVIRONMENT_PROMPT}. "
    "Use bash to solve tasks. Act, don't explain."
)


TOOLS = [
    {
        "name":"bash",
        "description": "Run a shell command",
        "input_schema":{
            "type":"object",
            "properties":{
                "command":{
                    "type":"string"
                }
            },
            "required":[]
        }
    }
]

def run_bash(command:str):
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any( d in command for d in dangerous):
        return "危险指令！！！！！！！！"
    
    try:
        r = subprocess.run(
            command,shell = True,
            cwd=os.getcwd(),
            capture_ouput = True,
            text = True,
            error = "replace",
            timeout = "120",
        )
        
        out = (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
        
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def agent_loop(messages:list):
    

