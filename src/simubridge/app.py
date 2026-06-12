"""
SimuBridge MCP Server — shared state and MATLAB engine management.

Holds the FastMCP instance, MATLAB engine lifecycle, and helpers
that tool modules import.
"""

import atexit
import io
import os
import base64
import shutil
import tempfile
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("simubridge")

# ---------------------------------------------------------------------------
# FastMCP instance — all tool modules register on this
# ---------------------------------------------------------------------------
mcp = FastMCP(
    name="simulink",
    instructions=(
        "SimuBridge MCP server. Provides tools to load, inspect, modify, and simulate "
        "Simulink models via a persistent MATLAB engine session.\n\n"
        "Tool reference:\n"
        "- open_model: open a .slx file\n"
        "- close_model: close a model (optionally save)\n"
        "- save_model: save the model\n"
        "- model_audit: read full model topology — all blocks + all connections "
        "(signal lines, Goto/From, Data Store); use this to explore structure and wiring\n"
        "- get_block_params: read all parameters of a block\n"
        "- get_block_ports: get port layout of a block (use before connecting)\n"
        "- get_model_config: read solver/stop-time/step-size settings\n"
        "- get_workspace_vars: read MATLAB base workspace variables\n"
        "- get_mfunction_code: read code inside a MATLAB Function block\n"
        "- describe_block: list all parameters of a library block (use before add_block)\n"
        "- search_library: find a block's library path by keyword\n"
        "- add_block: add a block from a library to the model\n"
        "- delete_block: delete a block (connected lines removed automatically)\n"
        "- connect: wire two block ports together\n"
        "- delete_line: remove a connection between two ports\n"
        "- set_block_params: set one or more block parameters\n"
        "- set_model_config: change solver or simulation settings\n"
        "- set_workspace_vars: write variables to MATLAB workspace\n"
        "- set_mfunction_code: write code into a MATLAB Function block\n"
        "- create_model: create a new blank model\n"
        "- create_subsystem: group blocks into a subsystem\n"
        "- expand_subsystem: flatten a subsystem into its parent\n"
        "- add_subsystem_port: add an Inport/Outport inside a subsystem\n"
        "- remove_subsystem_port: remove an Inport/Outport from a subsystem\n"
        "- simulate_and_analyze_waveform: run simulation and inspect logged signals\n"
        "- eval_matlab: execute arbitrary MATLAB code — use only when no other tool fits"
    ),
)

# ---------------------------------------------------------------------------
# MATLAB Engine Manager
# ---------------------------------------------------------------------------
_engine: Any = None

_SHARED_SESSION_NAME = "SIMULINK_MCP_SESSION"


def get_engine() -> Any:
    """Return the user's shared MATLAB session, connecting if necessary.

    Connects to the session the user's own MATLAB shares on startup (see
    startup.m: matlab.engine.shareEngine('SIMULINK_MCP_SESSION')), so every
    operation happens in the same process, workspace, and path the user sees —
    not a separate headless engine.
    """
    global _engine
    if _engine is not None:
        if not engine_is_alive():
            logger.warning("Connection to MATLAB session lost — reconnecting ...")
            _engine = None
    if _engine is None:
        import matlab.engine

        names = matlab.engine.find_matlab()
        if _SHARED_SESSION_NAME not in names:
            raise RuntimeError(
                f"Cannot find a shared MATLAB session named '{_SHARED_SESSION_NAME}'.\n"
                f"Open MATLAB and run:\n"
                f"    matlab.engine.shareEngine('{_SHARED_SESSION_NAME}')\n"
                f"To make this automatic on every MATLAB startup, add that line "
                f"to your startup.m (run 'edit(fullfile(userpath, \"startup.m\"))' "
                f"in MATLAB to open/create it), then restart MATLAB."
            )
        logger.info(f"Connecting to shared MATLAB session '{_SHARED_SESSION_NAME}' ...")
        _engine = matlab.engine.connect_matlab(_SHARED_SESSION_NAME)
        logger.info("Connected to MATLAB session.")
    return _engine


def restart_engine() -> Any:
    """Reconnect to the shared MATLAB session (recovery from a dropped connection).

    Does NOT call quit() — that session belongs to the user, not to us.
    """
    global _engine
    _engine = None
    return get_engine()


def engine_is_alive() -> bool:
    """Check whether the current engine session is responsive."""
    if _engine is None:
        return False
    try:
        out = io.StringIO()
        _engine.eval("1;", nargout=0, stdout=out, stderr=io.StringIO())
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helper: escape a string for embedding in MATLAB eval expressions
# ---------------------------------------------------------------------------
def escape_matlab(s: str) -> str:
    """Escape for safe embedding in MATLAB single-quoted string literals.

    Doubles single-quotes (MATLAB convention) and replaces ASCII control
    characters with ``char(N)`` expressions that close/reopen the surrounding
    single-quoted string.  The result is designed to be wrapped in ``'...'``
    by the caller.
    """
    s = s.replace("'", "''")
    # Handle all ASCII control chars (0x00-0x1F, 0x7F) that would break
    # MATLAB single-quoted string parsing
    for i in range(0, 32):
        ch = chr(i)
        if ch in s:
            s = s.replace(ch, f"' char({i}) '")
    if "\x7f" in s:
        s = s.replace("\x7f", "' char(127) '")
    return s


# ---------------------------------------------------------------------------
# Helper: safe eval — captures stdout/stderr, never leaks to real stdout
# ---------------------------------------------------------------------------
def matlab_eval(code: str, nargout: int = 0) -> tuple[Any, str, str]:
    """
    Evaluate *code* in the MATLAB engine.

    Returns (result, stdout_text, stderr_text).
    *result* is only meaningful when nargout > 0.
    """
    eng = get_engine()
    out = io.StringIO()
    err = io.StringIO()
    if nargout == 0:
        eng.eval(code, nargout=0, stdout=out, stderr=err)
        return None, out.getvalue(), err.getvalue()
    else:
        result = eng.eval(code, nargout=nargout, stdout=out, stderr=err)
        return result, out.getvalue(), err.getvalue()


def matlab_feval(func: str, *args: Any, nargout: int = 1) -> tuple[Any, str, str]:
    """Call a named MATLAB function via feval."""
    eng = get_engine()
    out = io.StringIO()
    err = io.StringIO()
    result = getattr(eng, func)(*args, nargout=nargout, stdout=out, stderr=err)
    return result, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Helper: capture all open figures as PNG bytes
# ---------------------------------------------------------------------------
FIGURE_TEMP_DIR = tempfile.mkdtemp(prefix="simubridge_figs_")
atexit.register(lambda: shutil.rmtree(FIGURE_TEMP_DIR, ignore_errors=True))


def capture_figures(dpi: int = 100, close_after: bool = True) -> list[tuple[bytes, str]]:
    """
    Save every open MATLAB figure to a temp PNG and return a list of
    (png_bytes, figure_name) tuples.
    """
    eng = get_engine()
    out = io.StringIO()
    err = io.StringIO()

    eng.eval("__mcp_figs = findobj('Type','figure');", nargout=0, stdout=out, stderr=err)
    n = int(eng.eval("length(__mcp_figs);", nargout=1, stdout=io.StringIO(), stderr=io.StringIO()))

    figures: list[tuple[bytes, str]] = []
    for i in range(1, n + 1):
        fname = os.path.join(FIGURE_TEMP_DIR, f"fig_{i}.png").replace("\\", "/")
        eng.eval(
            f"print(__mcp_figs({i}), '-dpng', '-r{dpi}', '{fname}');",
            nargout=0,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        with open(fname, "rb") as f:
            png_bytes = f.read()

        fig_name = eng.eval(
            f"num2str(__mcp_figs({i}).Number);",
            nargout=1,
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        figures.append((png_bytes, f"Figure {fig_name}"))

        try:
            os.remove(fname)
        except OSError:
            pass

    if close_after and n > 0:
        eng.eval("close all;", nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

    eng.eval("clear __mcp_figs;", nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
    return figures


def normalize_path(p: str) -> str:
    """Normalize a Windows path to forward slashes for MATLAB."""
    return p.replace("\\", "/")


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------
def set_workspace_var(name: str, value: Any) -> None:
    """Write a Python value into the MATLAB base workspace."""
    eng = get_engine()
    eng.workspace[name] = value


def set_workspace_vars(vars_dict: dict[str, Any]) -> str:
    """Write multiple variables into MATLAB base workspace from a dict."""
    eng = get_engine()
    for name, value in vars_dict.items():
        eng.workspace[name] = value
    return f"Set {len(vars_dict)} workspace variable(s): {', '.join(vars_dict.keys())}"


# ---------------------------------------------------------------------------
# Helper: safely convert MATLAB numeric to Python float
# ---------------------------------------------------------------------------
def matlab_to_float(val) -> float:
    """Convert a MATLAB numeric (or Python numeric) to a Python float."""
    try:
        return float(val)
    except (ValueError, TypeError):
        pass
    # MATLAB double: access via index
    try:
        return float(val[0])
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Block port helpers
# ---------------------------------------------------------------------------
def get_block_port_handles(block_path: str) -> tuple[list, list]:
    """Return (inport_handles, outport_handles) for a block."""
    eng = get_engine()
    ph = eng.get_param(
        block_path, "PortHandles",
        nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
    )
    import matlab
    inports = list(ph.Inport) if hasattr(ph, 'Inport') and ph.Inport else []
    outports = list(ph.Outport) if hasattr(ph, 'Outport') and ph.Outport else []
    return inports, outports


# ---------------------------------------------------------------------------
# General-purpose MATLAB execution
# ---------------------------------------------------------------------------
@mcp.tool()
def eval_matlab(code: str) -> str:
    """Execute arbitrary MATLAB code in the persistent engine.

    Use this for operations not covered by existing tools. The code runs
    in the same MATLAB session as the loaded model, so you can call any
    MATLAB function directly.

    Args:
        code: MATLAB code to execute. Use ';' to suppress output.
              Use newline to run multiple statements.
    """
    try:
        eng = get_engine()
        out_io = io.StringIO()
        err_io = io.StringIO()
        result = getattr(eng, 'evalc')(code, nargout=1,
                                       stdout=out_io, stderr=err_io)
        out = str(result).strip() if result else ""
        err_s = err_io.getvalue().strip()
        if err_s:
            out += f"\n[stderr] {err_s}"
        if not out:
            return "Executed (no output)."
        return out
    except Exception as e:
        return f"Error: {e}"
