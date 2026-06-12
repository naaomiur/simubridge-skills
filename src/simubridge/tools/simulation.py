"""Simulation — run models and analyze signal data."""

import io

from simubridge.app import (
    mcp, matlab_eval, escape_matlab, get_engine,
)


# ============================================================================
# Simulation + Signal Analysis — unified entry point
#
# Splitting "run" and "analyze" into separate tools added a forced two-call
# dance for no benefit: there is no waveform to inspect until a simulation
# has just run, so the two steps are always used together.
# ============================================================================

def _resolve_source(eng, var_name: str, signal_index: int) -> str:
    """Build MATLAB code that resolves a logged-signal Dataset into workspace vars.

    *var_name* always names a Simulink.SimulationData.Dataset — this tool
    always populates "logsout" itself before analyzing it.

    Sets: mcp_data, mcp_tout, mcp_name
    For signal_index=0 (list mode), sets: mcp_list (cell array of signal names + dims)
    """
    source = var_name if var_name else "logsout"

    if signal_index == 0:
        # List mode: show relative path + port + dims for every logged signal
        return (
            f"v = {source};"
            f"n = v.numElements;"
            f"c = {{}};"
            f"for k = 1:n;"
            f"  try;"
            f"    bp = v{{k}}.BlockPath.getBlock(1);"
            f"    parts = strsplit(bp, '/');"
            f"    rel = strjoin(parts(2:end), '/');"
            f"    pi = v{{k}}.PortIndex;"
            f"    mt = ''; try; mt = get_param(bp, 'MaskType'); catch; end;"
            f"    if strcmp(mt, 'Three-Phase VI Measurement');"
            f"      if pi == 1; tag = ':1 (Vabc)';"
            f"      elseif pi == 2; tag = ':2 (Iabc)';"
            f"      else; tag = sprintf(':%d', pi); end;"
            f"    else; tag = sprintf(':%d', pi); end;"
            f"    nm = [rel tag];"
            f"  catch; nm = sprintf('signal_%d', k); end;"
            f"  try; sz = size(v{{k}}.Values.Data);"
            f"    ds = sprintf('%dx%d', sz(1), sz(2));"
            f"  catch; ds = '?'; end;"
            f"  c{{k}} = sprintf('%d|%s|%s', k, nm, ds);"
            f"end;"
            f"assignin('base','mcp_list', c);"
            f"assignin('base','mcp_list_n', n);"
        )

    # Data extraction for a specific signal_index
    return (
        f"el = {source}{{{signal_index}}};"
        f"data = el.Values.Data;"
        f"tout = el.Values.Time(:);"
        f"try; nm = el.Name; if isempty(nm); nm = el.BlockPath.getBlock(1); end;"
        f"catch; nm = sprintf('signal_%d', {signal_index}); end;"
        f"if ndims(data) == 3; data = squeeze(data); end;"
        f"assignin('base','mcp_data', data);"
        f"assignin('base','mcp_tout', tout);"
        f"assignin('base','mcp_name', nm);"
    )


def _read_scalar(eng, varname: str) -> float:
    try:
        return float(eng.workspace[varname])
    except Exception:
        return float("nan")


@mcp.tool()
def simulate_and_analyze_waveform(
    model_name: str,
    signal_index: int = 1,
    var_name: str = "logsout",
    stop_time: str = "",
    solver: str = "",
) -> str:
    """Run a simulation and inspect a logged signal: centered-window envelope
    (digital scope view) — in one step.

    Only signals with "Log signal data" checked are captured to logsout.
    Outport blocks are NOT automatically captured.

    Each of 150 uniformly-spaced output points takes the max/min of raw data
    within ±10ms — one full 50Hz cycle. No filtering, no transforms, no
    interpolation. Multi-column signals shown in one table.

    Args:
        model_name: Name of the loaded Simulink model.
        signal_index: Signal index in Dataset (1-indexed). 0 = list all signals.
        var_name: Variable to analyze. Defaults to "logsout".
        stop_time: Simulation stop time (e.g. '0.1', '1.0').
        solver: Solver name (e.g. 'ode23tb', 'ode15s').
    """
    try:
        eng = get_engine()

        # ── Run simulation ──
        sim_cmd = (
            f"set_param('{escape_matlab(model_name)}',"
            f"'SignalLogging','on');"
        )
        if stop_time:
            sim_cmd += f"set_param('{escape_matlab(model_name)}','StopTime','{stop_time}');"
        if solver:
            sim_cmd += f"set_param('{escape_matlab(model_name)}','Solver','{solver}');"

        sim_cmd += (
            f"clear logsout;"  # prevent stale data from previous runs
            f"o = sim('{escape_matlab(model_name)}');"
            f"if isprop(o, 'logsout'); logsout = o.logsout;"
            f"else; logsout = Simulink.SimulationData.Dataset; end;"
            f"clear o;"
        )

        _, stdout, stderr = matlab_eval(sim_cmd, nargout=0)
        if stderr and "Warning:" not in stderr:
            return f"Simulation failed: {stderr[:500]}"

        source = var_name

        # ── Resolve data source ──
        res_code = _resolve_source(eng, var_name, signal_index)
        eng.eval(res_code, nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

        # ── signal_index=0: list mode ──
        if signal_index == 0:
            n = int(_read_scalar(eng, "mcp_list_n"))
            lines = [f"=== {source}: {n} signal(s) ==="]
            try:
                lst = eng.workspace["mcp_list"]
                for i in range(min(n, len(lst))):
                    raw = str(lst[i]).strip()
                    parts_raw = raw.split("|", 2)
                    if len(parts_raw) == 3:
                        idx, name, dims = parts_raw
                        lines.append(f"  [{idx}] {name} [{dims}]")
                    else:
                        lines.append(f"  [{i+1}] {raw}")
            except Exception:
                lines.append("  (unreadable)")
            eng.eval("clear mcp_list mcp_list_n;",
                     nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
            return "\n".join(lines)

        # ── Get signal name and dimensions ──
        sig_name = ""
        try:
            sig_name = str(eng.workspace["mcp_name"]).strip()
        except Exception:
            sig_name = f"signal_{signal_index}"

        eng.eval(
            "nc = size(mcp_data, 2); assignin('base','mcp_nc', nc);"
            "N = size(mcp_data, 1); assignin('base','mcp_N', N);",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        n_cols = int(_read_scalar(eng, "mcp_nc"))
        N = int(_read_scalar(eng, "mcp_N"))

        # ── Determine time info ──
        try:
            t_total = float(
                eng.eval("mcp_tout(end) - mcp_tout(1)", nargout=1,
                         stdout=io.StringIO(), stderr=io.StringIO())
            )
        except Exception:
            t_total = 0.0

        # ── Centered-window envelope: ±10ms (1 full 50Hz cycle) ──
        n_out = min(150, N)
        win_code = (
            f"data = mcp_data; tout = mcp_tout(:);"
            f"N = size(data, 1); nc = size(data, 2);"
            f"Ts = tout(2) - tout(1);"
            f"half = max(1, round(0.01 / Ts));"
            f"t_out = linspace(tout(1), tout(end), {n_out})';"
            f"mx = zeros({n_out}, nc); mn = zeros({n_out}, nc);"
            f"for i = 1:{n_out};"
            f"  [~, ic] = min(abs(tout - t_out(i)));"
            f"  i1 = max(1, ic - half); i2 = min(N, ic + half);"
            f"  for c = 1:nc;"
            f"    mx(i, c) = max(data(i1:i2, c));"
            f"    mn(i, c) = min(data(i1:i2, c));"
            f"  end;"
            f"end;"
            f"assignin('base','mcp_env_max', mx);"
            f"assignin('base','mcp_env_min', mn);"
            f"assignin('base','mcp_env_t', t_out);"
        )
        eng.eval(win_code, nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

        # ── Read back and build table ──
        table_code = (
            "t = mcp_env_t(:); mx = mcp_env_max; mn = mcp_env_min;"
            "nc = size(mx, 2);"
            "hdr = 'Time(s)       ';"
            "for c = 1:nc;"
            "  hdr = [hdr, sprintf('  Max_%-14d  Min_%-14d', c, c)];"
            "end;"
            "rows = cell(length(t), 1);"
            "for i = 1:length(t);"
            "  r = sprintf('%-14.6f', t(i));"
            "  for c = 1:nc;"
            "    r = [r, sprintf('  %-14.4f  %-14.4f', mx(i, c), mn(i, c))];"
            "  end;"
            "  rows{i} = r;"
            "end;"
            "assignin('base','mcp_tbl', [hdr, char(10), strjoin(rows, char(10))]);"
        )
        eng.eval(table_code, nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

        n_pts = int(float(str(matlab_eval("length(mcp_env_t);", nargout=1)[0]).strip()))
        tbl = str(eng.workspace["mcp_tbl"]).strip()

        # ── Build output ──
        lines = [f"=== {source}[{signal_index}] '{sig_name}' ==="]
        lines.append(f"Samples: {N} | Columns: {n_cols} | Duration: {t_total:.4f}s")
        lines.append(f"--- Envelope ({n_pts} pts, 20ms window) ---")
        lines.append(tbl)

        eng.eval(
            "clear mcp_data mcp_tout mcp_name mcp_nc mcp_N "
            "mcp_env_max mcp_env_min mcp_env_t mcp_tbl;",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


# ============================================================================
# Workspace tools
# ============================================================================

@mcp.tool()
def get_workspace_vars(var_names: str = "*") -> str:
    """Read variables from the MATLAB base workspace.

    Args:
        var_names: Comma-separated variable names to read (e.g. "S_base,f_g"),
                   or "*" to list all available variable names.
    """
    try:
        eng = get_engine()

        if var_names.strip() == "*":
            names_str, _, _ = matlab_eval("strjoin(who, ', ');", nargout=1)
            all_names = [n.strip() for n in str(names_str).split(",") if n.strip()]
            if not all_names:
                return "Workspace is empty."
            lines = [f"Workspace variables ({len(all_names)}):"]
            for name in all_names[:50]:
                try:
                    val = eng.workspace[name]
                    lines.append(f"  {name} = {val}")
                except Exception:
                    lines.append(f"  {name} = <unreadable>")
            if len(all_names) > 50:
                lines.append(f"  ... ({len(all_names) - 50} more)")
            return "\n".join(lines)

        names = [n.strip() for n in var_names.split(",") if n.strip()]
        if not names:
            return "No variable names provided."

        lines = []
        for name in names:
            try:
                val = eng.workspace[name]
                lines.append(f"  {name} = {val}")
            except KeyError:
                lines.append(f"  {name} = <not found>")
            except Exception as e:
                lines.append(f"  {name} = <error: {e}>")

        return "Workspace values:\n" + "\n".join(lines)

    except Exception as e:
        return f"Error reading workspace: {e}"
