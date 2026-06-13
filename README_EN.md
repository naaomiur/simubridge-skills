<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/MCP-1.2+-green.svg" alt="MCP">
  <img src="https://img.shields.io/badge/MATLAB-R2021a+-orange.svg" alt="MATLAB">
  <img src="https://img.shields.io/badge/license-MIT-purple.svg" alt="License">
  <br>
  <img src="https://img.shields.io/github/stars/naaomiur/simubridge-skills?style=social" alt="Stars">
</p>

# 🔗 SimuBridge

> AI-Powered Simulink Skill Pack with MCP Backend

[中文文档](README.md)

---

## What is this

`simubridge-skills` is a **Claude Code / Codex skill project** that lets AI assistants control MATLAB Simulink using natural language. It contains:

- 🎯 **Skill pack** (`skill/simubridge/`) — prompt bundle that teaches AI how to use Simulink tools effectively
- 🔧 **MCP server** (`src/simubridge/`) — local backend connecting to MATLAB Engine with 20+ tools

**The skill is the product. The MCP server is the backend.**

---

## Skill Index

| Skill | Status | Purpose | Trigger Keywords |
|-------|--------|---------|-----------------|
| [`simubridge`](skill/simubridge/README.md) | Stable | Simulink model creation, inspection, modification, and simulation | "Simulink", "open model", "add block", "connect", "simulate", "subsystem" |

---

## Quick Start

### Prerequisites

- **MATLAB R2021a+** with Simulink
- **Python 3.9–3.12**

### 1. Install MATLAB Engine for Python

```cmd
cd "C:\Program Files\MATLAB\R2024a\extern\engines\python"
python setup.py install
```

Verify: `python -c "import matlab.engine; print('OK')"`

> 💡 Permission error? Add `--user`. Python 3.13+? Downgrade to 3.11 or 3.12.

### 2. Install the MCP Backend

```bash
git clone https://github.com/naaomiur/simubridge-skills.git
cd simubridge-skills
pip install -e .
```

### 3. Configure MATLAB

Run in MATLAB:

```matlab
matlab.engine.shareEngine('SIMULINK_MCP_SESSION')
```

> 💡 Add to `startup.m` for auto-share on every launch:
> ```matlab
> edit(fullfile(userpath, 'startup.m'))
> ```

### 4. Install the Skill

The skill teaches Claude how to use Simulink tools effectively. Copy the entire folder (not just `SKILL.md`) — the `references/` directory is needed by the skill.

> ⚠️ Only copying `SKILL.md` will silently break the skill. Always copy the whole `skill/simubridge/` folder.

#### Claude Code (with MCP — full functionality)

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

Configure the MCP server (see Step 5), restart, and Claude can fully control Simulink.

#### Claude Code (standalone skill — no MATLAB needed)

Even without MATLAB or the MCP backend, you can still use the skill as a **Simulink knowledge base** for planning and discussion:

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

Start a Claude Code session and ask:

```
Read the simubridge skill. I'm designing a motor control system in Simulink —
suggest a block diagram layout with the right blocks and wiring topology.
```

Claude will read `SKILL.md` and `references/tool-guide.md` to give informed guidance — even without executing anything. This is useful for:

- Planning model architecture before building it
- Getting block library paths and parameter names for manual use
- Learning Simulink workflows and best practices
- Designing subsystem hierarchies and wiring strategies

> 💡 **How it works**: The skill provides Claude with detailed knowledge of every Simulink tool, common library paths, port types, and wiring patterns. Claude can then advise you on model design even when the MCP backend isn't running.

#### Codex

> ⚠️ Codex is not yet supported. We are working on Codex skill packaging. For now, use Claude Code.

### 5. Configure the MCP Server

The MCP server must be configured so the AI assistant can connect to it.

#### Claude Code

Add to `claude_desktop_config.json`:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

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

You can also copy the included [`claude_desktop_config.json`](claude_desktop_config.json) directly.

#### Codex

Add the same configuration in Codex's MCP settings panel.

#### Verify Installation

Restart your AI assistant. Start a new session and try:

```
Open mymodel.slx, add a Gain block set to 2.5 after the Voltage Source,
and connect it to a Scope
```

If everything is configured correctly, Claude will:
1. Recognize the Simulink task
2. Read the skill definitions from `SKILL.md`
3. Call MCP tools like `search_library`, `add_block`, `connect` to complete the task

---

## What the Skill Can Do

| Category | Tools | Description |
|----------|-------|-------------|
| **Model** | `open_model` / `create_model` / `close_model` / `save_model` | Model lifecycle |
| **Block** | `add_block` / `delete_block` / `search_library` / `describe_block` | Block management |
| **Param** | `get_block_params` / `set_block_params` / `get_model_config` / `set_model_config` | Parameter configuration |
| **Wiring** | `connect` / `delete_line` | Signal/power wiring (batch supported) |
| **Inspect** | `model_audit` / `get_block_ports` | Topology audit |
| **Stateflow** | `get_mfunction_code` / `set_mfunction_code` | MATLAB Function code |
| **Simulation** | `simulate_and_analyze_waveform` | Simulation + waveform analysis |
| **Workspace** | `get_workspace_vars` / `set_workspace_vars` | MATLAB workspace |
| **Subsystem** | `create_subsystem` / `expand_subsystem` / port management | Subsystem ops |
| **Escape** | `eval_matlab` | Arbitrary MATLAB execution |

> 📖 Complete tool documentation: [`skill/simubridge/SKILL.md`](skill/simubridge/SKILL.md)

---

## Architecture

```
┌─────────────────┐     Skill      ┌──────────────┐     MCP stdio     ┌──────────────┐   MATLAB API   ┌──────────┐
│  Claude / Codex  │ ◄────────────  │  simubridge   │ ◄──────────────► │  MCP Server   │ ◄────────────► │  MATLAB  │
│  + Skill Prompt  │                │  (skill def)  │                  │  (Python)     │                │(Simulink)│
└─────────────────┘                └──────────────┘                  └──────────────┘                └──────────┘
```

- **Skill layer**: `skill/simubridge/SKILL.md` — teaches AI how to use each tool
- **Transport**: MCP stdio — local process, no network
- **Engine**: `matlab.engine` API — connects to your running MATLAB session
- **Auto-save**: every write operation auto-saves the model

---

## Project Structure

```
simubridge-skills/
├── skill/simubridge/               # 🎯 Skill pack (primary)
│   ├── README.md                    #    Skill documentation
│   ├── SKILL.md                     #    Skill definition (bilingual tool reference)
│   └── references/
│       └── tool-guide.md            #    Quick reference
├── src/simubridge/                  # 🔧 MCP backend
│   ├── __init__.py                  #    Entry point + tool registration
│   ├── app.py                       #    FastMCP + MATLAB engine manager
│   └── tools/                       #    7 tool modules
├── examples/
│   └── basic_usage.md
├── pyproject.toml
├── claude_desktop_config.json
├── LICENSE
├── README.md                        #    Chinese version
└── README_EN.md                     #    English version (this file)
```

---

## License

MIT License — see [LICENSE](LICENSE).

> ⚠️ MATLAB and Simulink are registered trademarks of The MathWorks, Inc. This project is not affiliated with or endorsed by MathWorks.

---

## Acknowledgments

Built with [FastMCP](https://github.com/jlowin/fastmcp) and the [Model Context Protocol](https://modelcontextprotocol.io).
