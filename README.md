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

[English README](README_EN.md)

---

## 这是什么

`simubridge-skills` 是一个 **Claude Code / Codex 技能项目**，让 AI 助手能直接用自然语言操控 MATLAB Simulink。它包含：

- 🎯 **技能包**（`skill/simubridge/`）— 教 AI 如何高效使用 Simulink 工具的提示词集合
- 🔧 **MCP 服务端**（`src/simubridge/`）— 连接 MATLAB 引擎的本地后端，提供 20+ 个工具

**技能是主体，MCP 是后端。** 用户安装技能后，AI 就知道如何一步步构建、修改、仿真 Simulink 模型。

---

## 技能索引

| 技能 | 状态 | 用途 | 触发词 |
|-------|------|------|--------|
| [`simubridge`](skill/simubridge/README.md) | Stable | Simulink 模型创建、查看、修改、仿真 | "Simulink"、"打开模型"、"加个模块"、"连线"、"仿真"、"子系统" |

---

## 快速开始

### 环境要求

- **MATLAB R2021a+**（需包含 Simulink）
- **Python 3.9–3.12**（3.13+ 暂不支持 MATLAB 引擎）

### 1. 安装 MATLAB Python 引擎

> ⚠️ 必须完成！SimuBridge 通过 `matlab.engine` API 连接 MATLAB。

#### 步骤

在 MATLAB 中运行 `matlabroot` 获取安装路径（如 `C:\Program Files\MATLAB\R2024a`），然后在终端中：

```cmd
cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"
python setup.py install
```

验证：

```cmd
python -c "import matlab.engine; print('OK')"
```

#### 常见问题排查

| 错误信息 | 原因 | 解决方法 |
|------|------|------|
| `Install setuptools` / `ModuleNotFoundError: No module named 'setuptools'` | 缺少 setuptools | `python -m pip install setuptools` |
| `permission denied` / 权限不足 | 没有管理员权限 | `python setup.py install --user` |
| `supports Python version 3.9, 3.10, 3.11, and 3.12, but your version is 3.13` | Python 版本太高，MATLAB 引擎只支持 3.9–3.12 | 使用 Python 3.11/3.12 运行安装（见下方） |
| `'matlab' is not a package` | 当前目录有同名 matlab 文件夹冲突 | 换个目录运行验证命令 |

#### Python 3.13 用户的解决方案

MATLAB 引擎目前最高支持 Python 3.12。如果你的默认 Python 是 3.13，需要用一个 3.11/3.12 的 Python 来安装和运行。

安装 Python 3.11 或 3.12，记住安装路径（默认 `C:\Python311` 或 `C:\Users\你的用户名\AppData\Local\Programs\Python\Python311`），然后：

```cmd
# 找到你的 Python 安装路径，替换下面的 C:\Python311
C:\Python3.11\python.exe -m pip install setuptools
cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"
C:\Python3.11\python.exe setup.py install
C:\Python3.11\python.exe -c "import matlab.engine; print('OK')"
```

安装成功后，MCP 配置也要指向这个 Python：

```json
{
  "mcpServers": {
    "simubridge": {
      "command": "C:\\Python3.11\\python.exe",（你的python路径）
      "args": ["-m", "simubridge"]
    }
  }
}
```

如果没有旧版 Python，去 https://www.python.org/downloads/release/python-3119/ 下载安装 Python 3.11，取消勾选 "Add to PATH"。

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

> ⚠️ 只复制 `SKILL.md` 会导致技能静默失效。务必复制整个 `skill/simubridge/` 文件夹。

#### Claude Code（配合 MCP — 完整功能）

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

配置 MCP 服务端（见第 5 步），重启后 Claude 可以完整操控 Simulink。

#### Claude Code（独立技能 — 无需 MATLAB）

即使没有 MATLAB 和 MCP 后端，你仍然可以把技能当作 **Simulink 知识库**来规划和讨论：

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

启动 Claude Code 会话后说：

```
读取 simubridge 技能。我在设计一个电机控制系统，帮我规划模块布局和接线拓扑。
```

Claude 会读取 `SKILL.md` 和 `references/tool-guide.md`，即使不执行任何操作也能给出专业建议。适用于：

- 搭建模型前规划架构
- 获取模块的库路径和参数名，手动操作时参考
- 学习 Simulink 工作流和最佳实践
- 设计子系统层级和连线策略

> 💡 **工作原理**：技能文件包含每个 Simulink 工具的详细说明、常用库路径、端口类型和连线模式。Claude 即使不连 MCP，也能基于这些知识帮你设计模型。

#### Codex

> ⚠️ Codex 暂不支持。我们正在开发 Codex 技能包。目前请使用 Claude Code。

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

> 📖 完整中英双语工具说明：[`skill/simubridge/SKILL.md`](skill/simubridge/SKILL.md)

---

## 架构

```
┌─────────────────┐     技能       ┌──────────────┐    MCP stdio     ┌──────────────┐  MATLAB API  ┌──────────┐
│  Claude / Codex  │ ◄───────────  │  simubridge   │ ◄──────────────► │  MCP Server   │ ◄───────────► │  MATLAB  │
│  + 技能提示词     │               │  (技能定义)    │                  │  (Python 后端) │               │(Simulink)│
└─────────────────┘               └──────────────┘                  └──────────────┘               └──────────┘
```

- **技能层**：`skill/simubridge/SKILL.md` — 教 AI 每个工具的用途和参数
- **传输层**：MCP stdio — 本地进程通信，无网络依赖
- **引擎层**：`matlab.engine` API — 连接你正在使用的 MATLAB 会话
- **自动保存**：每次写入操作后自动保存，GUI 中立即可见

---

## 项目结构

```
simubridge-skills/
├── skill/simubridge/               # 🎯 技能包（主体）
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
├── README.md                        #    中文版（本文件）
└── README_EN.md                     #    英文版
```

---

## 开源协议

MIT License — 详见 [LICENSE](LICENSE)。

> ⚠️ MATLAB 和 Simulink 是 The MathWorks, Inc. 的注册商标。本项目与 MathWorks 无关，亦未获其背书。

---

## 致谢

基于 [FastMCP](https://github.com/jlowin/fastmcp) 和 [Model Context Protocol](https://modelcontextprotocol.io) 构建。
