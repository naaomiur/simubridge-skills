# SimuBridge · Simulink AI Skill

> AI 驱动的 Simulink 模型操作技能 · AI-Powered Simulink Model Manipulation Skill

This skill teaches Claude (or any AI assistant) to create, inspect, modify, wire, and simulate MATLAB Simulink models using natural language. It is backed by the **SimuBridge MCP server** — a local process that connects the AI to your MATLAB session.

---

## 🎯 What this skill does

| 分类 | 能力 |
|------|------|
| **模型** | 打开/新建/保存/关闭 .slx 文件 |
| **模块** | 搜索库模块、添加（单个/批量）、删除 |
| **参数** | 读写模块参数、求解器配置 |
| **连线** | 连接信号线/功率端口、删除连线、支持批量 |
| **检查** | 完整拓扑审计（块+四种连线+未连接端口） |
| **Stateflow** | 读写 MATLAB Function 块代码 |
| **仿真** | 运行仿真 + 波形分析 |
| **子系统** | 打包/展开、端口管理 |
| **MATLAB** | 执行任意 MATLAB 代码 |

---

## 📦 Installation

### Prerequisites

- MATLAB R2021a+ with Simulink
- Python 3.9–3.12
- MATLAB Engine for Python installed

### 1. Install the MCP backend

```bash
git clone https://github.com/naaomiur/simubridge-skills.git
cd simubridge-skills
pip install -e .
```

### 2. Share MATLAB engine

In MATLAB:
```matlab
matlab.engine.shareEngine('SIMULINK_MCP_SESSION')
```

### 3. Install the skill

**Claude Code:**
```bash
cp -R skill/simubridge ~/.claude/skills/
```

**Codex:**
```bash
cp -R skill/simubridge ~/.codex/skills/
```

### 4. Configure MCP in your AI assistant

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

---

## 📂 Skill structure

```
skill/simubridge/
├── SKILL.md              # 技能定义 · Skill definition (中英双语工具详解)
├── README.md             # 本文件 · This file
└── references/
    └── tool-guide.md     # 工具速查 · Quick reference
```

---

## 🛠️ Tool overview

See [`SKILL.md`](SKILL.md) for complete bilingual tool documentation with parameters and notes.

| Tool | Description |
|------|-------------|
| `open_model` / `create_model` / `close_model` / `save_model` | Model operations |
| `add_block` / `delete_block` | Block add/delete (single or batch) |
| `search_library` / `describe_block` | Library search and inspection |
| `get_block_params` / `set_block_params` | Parameter read/write |
| `get_model_config` / `set_model_config` | Solver configuration |
| `connect` / `delete_line` | Wiring (signal/power, batch) |
| `model_audit` / `get_block_ports` | Topology audit + port inspection |
| `get_mfunction_code` / `set_mfunction_code` | Stateflow code |
| `simulate_and_analyze_waveform` | Simulation + waveform |
| `get_workspace_vars` / `set_workspace_vars` | MATLAB workspace |
| `create_subsystem` / `expand_subsystem` | Subsystem management |
| `add_subsystem_port` / `remove_subsystem_port` | Subsystem port management |
| `eval_matlab` | Arbitrary MATLAB execution |
