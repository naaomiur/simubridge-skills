<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.2+-green.svg" alt="MCP">
  <img src="https://img.shields.io/badge/MATLAB-R2021a+-orange.svg" alt="MATLAB">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License">
  <br>
  <img src="https://img.shields.io/github/stars/naaomiur/simubridge-skills?style=social" alt="Stars">
</p>

# 🔗 SimuBridge

> AI 驱动的 Simulink 技能包 + MCP 后端

[English README](README.md)

---

## 这是什么

`simubridge-skills` 是一个 **Claude Code / Codex 技能项目**，让 AI 助手能直接用自然语言操控 MATLAB Simulink。它包含：

- 🎯 **技能包**（`skills/simubridge/`）— 教 AI 如何高效使用 Simulink 工具的提示词集合
- 🔧 **MCP 服务端**（`src/simubridge/`）— 连接 MATLAB 引擎的本地后端，提供 20+ 个工具

**技能是主体，MCP 是后端。** 用户安装技能后，AI 就知道如何一步步构建、修改、仿真 Simulink 模型。

---

## 技能索引

| 技能 | 状态 | 用途 | 触发词 |
|-------|------|------|--------|
| [`simubridge`](skills/simubridge/README.md) | Stable | Simulink 模型创建、查看、修改、仿真 | "Simulink"、"打开模型"、"加个模块"、"连线"、"仿真"、"子系统" |

---

## 快速开始

### 环境要求

- **MATLAB R2021a+**（需包含 Simulink）
- **Python 3.9–3.12**（3.13+ 暂不支持 MATLAB 引擎）

### 1. 安装 MATLAB Python 引擎

> ⚠️ 必须完成！SimuBridge 通过 `matlab.engine` API 连接 MATLAB。

在 MATLAB 中运行 `matlabroot` 获取安装路径（如 `C:\Program Files\MATLAB\R2024a`），然后在终端中：

```cmd
cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"
python setup.py install
```

验证：`python -c "import matlab.engine; print('OK')"`

> 💡 权限错误加 `--user`；Python 3.13+ 需降级到 3.11 或 3.12。

### 2. 安装 MCP 后端

```bash
git clone https://github.com/naaomiur/simubridge-skills.git
cd simubridge-skills
pip install -e .
```

### 3. 配置 MATLAB 共享引擎

在 MATLAB 命令窗口中运行：

```matlab
matlab.engine.shareEngine('SIMULINK_MCP_SESSION')
```

> 💡 建议写入 `startup.m` 每次自动共享：
> ```matlab
> edit(fullfile(userpath, 'startup.m'))
> ```
> 在打开的文件中添加 `matlab.engine.shareEngine('SIMULINK_MCP_SESSION');`，保存并重启 MATLAB。

### 4. 安装技能

技能文件教 Claude 如何高效使用 Simulink 工具。**必须复制整个文件夹**（不能只复制 `SKILL.md`）——`references/` 目录是技能需要的。

> ⚠️ 只复制 `SKILL.md` 会导致技能静默失效。务必复制整个 `skills/simubridge/` 文件夹。

#### Claude Code

```bash
# 如果目录不存在则创建
mkdir -p ~/.claude/skills

# 复制整个技能文件夹（不要只复制 SKILL.md）
cp -R skills/simubridge ~/.claude/skills/
```

复制完成后，技能在**项目级别**生效。启动新的 Claude Code 会话，直接用自然语言提问：

```
打开 mymodel.slx，在 Voltage Source 后面加一个 Gain 模块，增益设为 2.5
```

Claude Code 检测到 Simulink 相关请求时，会自动从技能文件夹读取 `SKILL.md`。MCP 服务端提供实际工具，技能教 Claude 如何正确使用它们。

> 💡 **工作原理**：MCP 服务端通过 `@mcp.tool()` 装饰器注册工具——Claude 自动发现它们。技能（`SKILL.md`）提供上下文：每个工具做什么、需要什么参数、如何组合使用。没有技能，Claude 也能调用工具，但可能不知道最优操作流程。

#### Codex

```bash
cp -R skills/simubridge ~/.codex/skills/
```

### 5. 配置 MCP 服务端

MCP 服务端需要配置好，AI 助手才能连接。

#### Claude Code

添加到 `claude_desktop_config.json`：

- **Windows**：`%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**：`~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "simubridge": {
      "command": "python",
      "args": ["-m", "simubridge"]
    }
  }
}
```

也可以直接复制仓库中附带的 [`claude_desktop_config.json`](claude_desktop_config.json)。

#### Codex

在 Codex 的 MCP 设置面板中添加同样配置。

#### 验证安装

重启 AI 助手，新建会话试试：

```
打开 mymodel.slx，在 Voltage Source 后面加一个 Gain 模块，增益设为 2.5，连到 Scope
```

配置正确的话，Claude 会：
1. 识别 Simulink 任务
2. 从 `SKILL.md` 读取技能定义
3. 依次调用 `search_library`、`add_block`、`connect` 等 MCP 工具完成任务

---

## 技能能力

| 分类 | 工具 | 功能 |
|------|------|------|
| **模型** | `open_model` / `create_model` / `close_model` / `save_model` | 模型生命周期 |
| **模块** | `add_block` / `delete_block` / `search_library` / `describe_block` | 模块管理 |
| **参数** | `get_block_params` / `set_block_params` / `get_model_config` / `set_model_config` | 参数配置 |
| **连线** | `connect` / `delete_line` | 信号/功率连线（支持批量） |
| **检查** | `model_audit` / `get_block_ports` | 拓扑审计 |
| **Stateflow** | `get_mfunction_code` / `set_mfunction_code` | MATLAB Function 代码读写 |
| **仿真** | `simulate_and_analyze_waveform` | 仿真 + 波形分析 |
| **工作区** | `get_workspace_vars` / `set_workspace_vars` | MATLAB 工作区读写 |
| **子系统** | `create_subsystem` / `expand_subsystem` / 端口管理 | 子系统操作 |
| **万能** | `eval_matlab` | 执行任意 MATLAB 代码 |

> 📖 完整中英双语工具说明：[`skills/simubridge/SKILL.md`](skills/simubridge/SKILL.md)

---

## 架构

```
┌─────────────────┐     技能       ┌──────────────┐    MCP stdio     ┌──────────────┐  MATLAB API  ┌──────────┐
│  Claude / Codex  │ ◄───────────  │  simubridge   │ ◄──────────────► │  MCP Server   │ ◄───────────► │  MATLAB  │
│  + 技能提示词     │               │  (技能定义)    │                  │  (Python 后端) │               │(Simulink)│
└─────────────────┘               └──────────────┘                  └──────────────┘               └──────────┘
```

- **技能层**：`skills/simubridge/SKILL.md` — 教 AI 每个工具的用途和参数
- **传输层**：MCP stdio — 本地进程通信，无网络依赖
- **引擎层**：`matlab.engine` API — 连接你正在使用的 MATLAB 会话
- **自动保存**：每次写入操作后自动保存，GUI 中立即可见

---

## 项目结构

```
simubridge-skills/
├── skills/simubridge/               # 🎯 技能包（主体）
│   ├── README.md                    #    技能说明
│   ├── SKILL.md                     #    技能定义（中英双语工具详解）
│   └── references/
│       └── tool-guide.md            #    工具速查表
├── src/simubridge/                  # 🔧 MCP 后端
│   ├── __init__.py                  #    入口 + 工具注册
│   ├── app.py                       #    FastMCP + MATLAB 引擎管理
│   └── tools/                       #    7 个工具模块
├── examples/
│   └── basic_usage.md               #    使用示例
├── pyproject.toml
├── claude_desktop_config.json
├── LICENSE
├── README.md                        #    英文版
└── README_CN.md                     #    中文版（本文件）
```

---

## 开源协议

MIT License — 详见 [LICENSE](LICENSE)。

> ⚠️ MATLAB 和 Simulink 是 The MathWorks, Inc. 的注册商标。本项目与 MathWorks 无关，亦未获其背书。

---

## 致谢

基于 [FastMCP](https://github.com/jlowin/fastmcp) 和 [Model Context Protocol](https://modelcontextprotocol.io) 构建。
