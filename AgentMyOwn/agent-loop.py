
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
        ##清理shell输出的正常输出和错误输出
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
        
    except (FileNotFoundError, OSError) as e:
        return f"Error: {e}"

def agent_loop(messages:list):
    while True :
        response = client.message.create(
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
        
        tool_call = []
        
        for block in response.content:
            if block.type == "tool_use":
                tool_call.append(block)
                
        
        if not tool_calls:
            return 
        
        results = []
        
        for block in tool_calls:
             print(f"\033[33m$ {block.input['command']}\033[0m")
             output= run_bash(block.input["command"])
             print(output[:200])
             results.append({
                 "type":"tool_result",
                "tool_use_id" :"block.if=id",
                "content":output 
             })
             
            #  拿到本轮的回答进行组装 
if __name__ == "__main__":
    print("s01: Agent Loop")
    print("Enter a question, press Enter to send. Type q to quit.\n")

    history = []
    while True:
        try:
            # \001/\002 tell Readline the ANSI escapes have zero display width.
            query = input("\001\033[36m\002s01 >> \001\033[0m\002")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit", ""):
            break
        history.append({"role": "user", "content": query})
        agent_loop(history)
        # Print the model's final text response
        response_content = history[-1]["content"]
        if isinstance(response_content, list):
            for block in response_content:
                if getattr(block, "type", None) == "text":
                    print(block.text)
        print()           