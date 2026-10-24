# learn-claude-code · 手搓 Claude Code 核心源码

> 一个从 0 到 1 手写的、类 Claude Code 的 Agent Harness，开源分享。
> 代码里难免还有错误和不够严谨的地方，欢迎大家批评指正、一起完善。

## 关于本项目

我自己动手实现了一套 Claude Code 的核心源码，覆盖了从 Agent 内核、上下文管理、记忆，到工具控制、子代理、技能加载、多智能体、MCP 插件与工具注册表等几乎完整的能力链路。所有实现尽量保持可读、可运行、可拆解，方便学习和二次开发。

核心入口是 `AgentMyOwn/agent-loop.py`，一个完整的 agent loop 实现。

## 已实现能力

- Agent 内核 / 主循环
- 工具调用与工具控制（bash、read_file、write_file、edit_file、glob 等）
- 权限控制与 Hooks 钩子
- TodoWrite 任务清单、Subagent 子代理、Skill 技能加载
- 上下文压缩与记忆
- 任务系统、后台任务、定时调度
- 多智能体团队与协议
- MCP 插件与工具注册表
- 集成 Harness、工作流运行时、Goal Loop

## 快速开始

1. 安装依赖：`pip install -r requirements.txt`
2. 配置环境变量：复制 `.env.example` 为 `.env`，填入 `ANTHROPIC_API_KEY` 和 `MODEL_ID`
3. 运行：`python AgentMyOwn/agent-loop.py`

更详细的分步教程与说明见 `docs/` 目录。

## 致谢

特别感谢 langchain code 项目，本项目参考并基于它的实现思路手搓而成。

本项目 fork 自 `shareAI-lab/learn-claude-code`，沿用其 MIT License。

## 联系我

- 邮箱：`3211840032@qq.com`

欢迎提 Issue / PR，也欢迎直接邮件交流。