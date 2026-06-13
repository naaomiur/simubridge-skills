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
- **Python 3.9–3.12**（⚠️ 3.13 不支持 MATLAB 引擎）

---

### 第 1 步：准备正确的 Python 版本

MATLAB 引擎**只支持 Python 3.9–3.12**。如果你的默认 Python 是 3.13+，需要单独安装一个 3.11/3.12。

> 本教程以 Python 3.12 为例，安装到 `P:\code\Python3.12`。你也可以用 3.11（`C:\Python311`）。

```cmd
# 确认你的 Python 版本
python --version
```

如果显示 `3.13.x`，从 https://www.python.org 下载安装 Python 3.12，**取消勾选 "Add to PATH"**，安装到自定义路径（如 `P:\code\Python3.12`）。

---

### 第 2 步：安装 MATLAB Python 引擎

在 MATLAB 中运行 `matlabroot` 获取安装路径，然后用你准备好的 Python 安装引擎：

```cmd
# 先装 setuptools
P:\code\Python3.12\python.exe -m pip install setuptools

# 进入 MATLAB 引擎目录（路径换成你的）
cd "你的MATLAB路径\extern\engines\python"
P:\code\Python3.12\python.exe setup.py install
```

验证：

```cmd
P:\code\Python3.12\python.exe -c "import matlab.engine; print('OK')"
```

#### 常见问题

| 错误 | 原因 | 解决 |
|------|------|------|
| `Install setuptools` | 缺少 setuptools | `python -m pip install setuptools` |
| `permission denied` | 无管理员权限 | `python setup.py install --user` |
| `supports Python 3.9–3.12, but your version is 3.13` | Python 版本太高 | 用第 1 步装的 3.12 运行 |
| `'matlab' is not a package` | 当前目录冲突 | 换个目录运行验证命令 |

---

### 第 3 步：安装 MCP 后端

```bash
git clone https://github.com/naaomiur/simubridge-skills.git
cd simubridge-skills

# 用你准备好的 Python 安装
P:\code\Python3.12\python.exe -m pip install -e .
```

验证：

```cmd
P:\code\Python3.12\python.exe -m simubridge
```

> ⚠️ 终端会卡住不退出——这是正常的，MCP 在等待 stdio 连接。按 `Ctrl+C` 停掉。

---

### 第 4 步：配置 Claude Code MCP

编辑 `C:\Users\你的用户名\.claude.json`，在 `"mcpServers"` 中添加：

```json
"simubridge": {
  "command": "P:\\code\\Python3.12\\python.exe",
  "args": ["-m", "simubridge"]
}
```

> ⚠️ JSON 不支持注释，不要把说明文字写进去。路径里反斜杠要双写 `\\`。

完整示例：

```json
{
  "mcpServers": {
    "simubridge": {
      "command": "P:\\code\\Python3.12\\python.exe",
      "args": ["-m", "simubridge"]
    }
  }
}
```

保存后**重启 Claude Code**。

---

### 第 5 步：验证 MCP 连接

在 Claude Code 中输入：

```
/mcp
```

看到 `simubridge` 显示**绿色 Connected** 即成功。26 个工具自动加载。

---

### 第 6 步：配置 MATLAB 共享引擎

在 MATLAB 命令窗口中运行：

```matlab
matlab.engine.shareEngine('SIMULINK_MCP_SESSION')
```

> 💡 写入 `startup.m` 每次启动自动共享：
> ```matlab
> edit(fullfile(userpath, 'startup.m'))
> ```

---

### 第 7 步：安装技能

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

技能教 Claude 如何高效使用 Simulink 工具。即使不装也能用（MCP 自带工具描述），装了效果更好。

---

### 开始使用

在 Claude Code 中试试：

```
打开 mymodel.slx，在 Voltage Source 后面加一个 Gain 模块，增益 2.5，连到 Scope
```

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
