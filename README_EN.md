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
- **Python 3.9–3.12** (⚠️ 3.13 not supported by MATLAB Engine)

---

### Step 1: Get the Right Python Version

MATLAB Engine **only supports Python 3.9–3.12**. If your default Python is 3.13+, install a separate 3.11 or 3.12.

> This tutorial uses Python 3.12 installed to `C:\Python312`. You can also use 3.11 (`C:\Python311`).

```cmd
# Check your Python version
python --version
```

If it says `3.13.x`, download Python 3.12 from https://www.python.org, **uncheck "Add to PATH"**, install to a custom path.

---

### Step 2: Install MATLAB Engine for Python

Run `matlabroot` in MATLAB to get the install path, then install with your prepared Python:

```cmd
# Install setuptools first
C:\Python312\python.exe -m pip install setuptools

# Navigate to MATLAB engine directory (replace with your path)
cd "your-MATLAB-path\extern\engines\python"
C:\Python312\python.exe setup.py install
```

Verify:

```cmd
C:\Python312\python.exe -c "import matlab.engine; print('OK')"
```

#### Troubleshooting

| Error | Cause | Fix |
|------|------|------|
| `Install setuptools` | setuptools missing | `python -m pip install setuptools` |
| `permission denied` | No admin rights | `python setup.py install --user` |
| `supports Python 3.9–3.12, but your version is 3.13` | Python too new | Use the Python 3.12 from Step 1 |
| `'matlab' is not a package` | Directory conflict | Run verify from a different directory |

---

### Step 3: Install the MCP Backend

```bash
git clone https://github.com/naaomiur/simubridge-skills.git
cd simubridge-skills

# Install with your prepared Python
C:\Python312\python.exe -m pip install -e .
```

Verify:

```cmd
C:\Python312\python.exe -m simubridge
```

> ⚠️ The terminal will hang — this is normal, MCP is waiting for stdio. Press `Ctrl+C` to stop.

---

### Step 4: Configure Claude Code MCP

Edit `C:\Users\<username>\.claude.json`, add under `"mcpServers"`:

```json
"simubridge": {
  "command": "C:\\Python312\\python.exe",
  "args": ["-m", "simubridge"]
}
```

> ⚠️ JSON doesn't support comments. Double backslashes `\\` in paths.

Full example:

```json
{
  "mcpServers": {
    "simubridge": {
      "command": "C:\\Python312\\python.exe",
      "args": ["-m", "simubridge"]
    }
  }
}
```

Save and **restart Claude Code**.

---

### Step 5: Verify MCP Connection

In Claude Code, run:

```
/mcp
```

`simubridge` should show **green Connected** with 26 tools loaded.

---

### Step 6: Configure MATLAB

In MATLAB command window:

```matlab
matlab.engine.shareEngine('SIMULINK_MCP_SESSION')
```

> 💡 Add to `startup.m` for auto-share:
> ```matlab
> edit(fullfile(userpath, 'startup.m'))
> ```

---

### Step 7: Install the Skill (Recommended)

```bash
mkdir -p ~/.claude/skills
cp -R skill/simubridge ~/.claude/skills/
```

The skill teaches Claude how to use Simulink tools effectively. MCP works without it, but the skill improves results.

---

### Try It

In Claude Code:

```
Open mymodel.slx, add a Gain block set to 2.5 after the Voltage Source,
and connect it to a Scope
```

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
