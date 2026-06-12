"""Model modification — set parameters, add/connect/delete blocks."""

import io
import json
import re

from simubridge.app import (
    mcp, matlab_eval, escape_matlab, get_engine, matlab_to_float,
    set_workspace_vars as _set_workspace_vars,
)

# Simulink GUI sometimes shows different names for solvers than the set_param API
# accepts.  These aliases translate common GUI names to their API equivalents.
_SOLVER_ALIASES: dict[str, str] = {
    "Discrete (no continuous states)": "FixedStepDiscrete",
    "discrete": "FixedStepDiscrete",
    "discrete (no continuous states)": "FixedStepDiscrete",
}


def _normalize(s: str) -> str:
    """Strip separators and lowercase for fuzzy enum matching."""
    return re.sub(r"[\s\-_]+", "", s).lower()


def _get_enum_values(eng, target_path: str, param_name: str) -> list[str]:
    """Return valid enum values for *param_name* on *target_path*.

    Returns an empty list when the parameter does not exist or is not an
    enum — callers can treat empty as “no enum constraint”.
    """
    try:
        bp = escape_matlab(target_path)
        pn = escape_matlab(param_name)
        eng.eval(
            f"p=get_param('{bp}','ObjectParameters');"
            f"if isfield(p,'{pn}')&&strcmp(p.('{pn}').Type,'enum');"
            f"  ev=p.('{pn}').Enum;"
            f"else; ev={{}}; end;",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        ev = eng.workspace["ev"]
        if ev:
            return [str(x) for x in ev]
    except Exception:
        pass
    return []


def _save_model(model_name: str) -> None:
    """Auto-save after every write so the user sees changes in the GUI."""
    try:
        matlab_eval(f"save_system('{escape_matlab(model_name)}');")
    except Exception:
        pass


@mcp.tool()
def set_block_params(
    block_path: str,
    params_json: str = "",
    param_name: str = "",
    param_value: str = "",
) -> str:
    """Set one or more parameters on a Simulink block.

    Single param:  set_block_params("mymodel/Gain", param_name="Gain", param_value="2.5")
    Batch:         set_block_params("mymodel/Gain", params_json='{"Gain": "2.5", "SampleTime": "1e-5"}')
    """
    if param_name and params_json:
        return "Provide either param_name+param_value or params_json, not both."

    if param_name:
        param_dict = {param_name: param_value}
    elif params_json:
        try:
            import json as _json
            param_dict = _json.loads(params_json)
        except Exception as e:
            return f"Invalid JSON in params_json: {e}"
    else:
        return "Provide either param_name+param_value or params_json."

    eng = get_engine()
    errors: list[str] = []
    ok_count = 0

    for key, value in param_dict.items():
        try:
            val_str = str(value)

            # Fuzzy-match enum values
            ev = _get_enum_values(eng, block_path, key)
            if ev:
                norm_val = _normalize(val_str)
                matches = [v for v in ev if _normalize(v) == norm_val]
                if len(matches) == 1:
                    val_str = matches[0]
                else:
                    errors.append(
                        f"  {key}: '{val_str}' is not valid. "
                        f"Allowed: {', '.join(ev)}"
                    )
                    continue

            eng.set_param(block_path, key, val_str,
                          nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
            ok_count += 1
        except Exception as e:
            errors.append(f"  {key}: {e}")

    parts = [f"Set {ok_count}/{len(param_dict)} parameter(s) on '{block_path}'."]
    if errors:
        parts.append(f"Failed {len(errors)}:\n" + "\n".join(errors))
    _save_model(block_path.split("/")[0])
    return "\n".join(parts)


def _ensure_sf_helper(eng) -> str:
    """Create a MATLAB .m helper that wraps sfroot calls.

    All Stateflow interactions happen inside MATLAB, avoiding COM
    encoding issues with sfroot on non-English Windows.

    Uses a fixed directory so old versions don't accumulate on the
    MATLAB path; `clear('mcp_set_mf_code')` forces re-resolution.
    """
    import os as _os

    set_helper = r"""function mcp_set_mf_code(block_path, file_path)
    rt = sfroot();
    m = rt.find('-isa','Stateflow.Machine');
    model_name = strtok(block_path, '/');
    target_chart = [];
    for i = 1:length(m)
        if strcmp(m(i).Name, model_name)
            charts = m(i).find('-isa','Stateflow.EMChart');
            for j = 1:length(charts)
                if strcmp(charts(j).Path, block_path)
                    target_chart = charts(j);
                    break;
                end
            end
            break;
        end
    end
    if isempty(target_chart)
        error('Chart not found: %s', block_path);
    end

    new_script = fileread(file_path);

    % If the new code does NOT start with "function", preserve the existing
    % function signature from the chart.  This avoids overwriting a named
    % signature like "function v_ref = fcn(theta_m, theta_g, ...)" with the
    % default "function y = fcn(u)".
    new_trimmed = strtrim(new_script);
    if ~startsWith(new_trimmed, 'function')
        old = target_chart.Script;
        nl = find(old == sprintf('\n'), 1);
        if isempty(nl)
            sig = old;  % one-liner — use as-is
        else
            sig = old(1:nl-1);
        end
        new_script = [sig sprintf('\n') new_script];
    end

    target_chart.Script = new_script;
end
"""
    get_helper = r"""function code = mcp_get_mf_code(block_path)
    bh = get_param(block_path, 'Handle');
    chartId = sf('Private', 'block2chart', bh);
    if chartId == 0
        error('Chart not found: %s', block_path);
    end
    chartObj = sf('IdToHandle', chartId);
    code = chartObj.Script;
end
"""
    d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_sf_helper_")
    _os.makedirs(d, exist_ok=True)

    for name, code in [("mcp_set_mf_code", set_helper), ("mcp_get_mf_code", get_helper)]:
        p = _os.path.join(d, f"{name}.m").replace("\\", "/")
        current = ""
        try:
            with open(p, "r", encoding="utf-8") as f:
                current = f.read()
        except Exception:
            pass
        if current != code:
            with open(p, "w", encoding="utf-8") as f:
                f.write(code)

    eng.eval(
        f"addpath('{d.replace(chr(92), '/')}'); clear('mcp_set_mf_code', 'mcp_get_mf_code');",
        nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
    )
    return d


@mcp.tool()
def set_mfunction_code(block_path: str, code: str) -> str:
    """Set the MATLAB code inside a MATLAB Function block.

    Use this to write compact algorithms (PLL, power control, AVR, etc.)
    inside a single MATLAB Function block instead of wiring dozens of
    individual Gain / Sum / Product / Integrator blocks.

    The code must be a valid MATLAB function body.  The function signature
    is inferred from the block's existing inputs/outputs — you only need
    to provide the body (everything after the function signature line).

    Example for a PLL with inputs (v_alpha, v_beta) and outputs (omega_g, theta_g):
        set_mfunction_code("model/PLL", '''
            persistent theta_g_int omega_g_int vq_int
            if isempty(theta_g_int)
                theta_g_int = 0; omega_g_int = 2*pi*50; vq_int = 0;
            end
            Ts = 1e-5; Kp = 9; Ki = 5.5; Vbase = 433.01; wn = 2*pi*50;
            vd = v_alpha*cos(theta_g_int) + v_beta*sin(theta_g_int);
            vq = -v_alpha*sin(theta_g_int) + v_beta*cos(theta_g_int);
            vq_norm = vq / (sqrt(2)*Vbase);
            vq_int = vq_int + Ki*Ts*vq_norm;
            domega = Kp*vq_norm + vq_int;
            omega_g = wn + domega;
            theta_g_int = theta_g_int + omega_g*Ts;
            if theta_g_int > 2*pi, theta_g_int = theta_g_int - 2*pi; end
            theta_g = theta_g_int;
        ''')

    Args:
        block_path: Full path to the MATLAB Function block (e.g. 'model/PLL').
        code: MATLAB code for the function body (no function signature needed).

    Returns:
        Confirmation or error message.
    """
    import tempfile
    import os as _os

    try:
        eng = get_engine()

        # Ensure the sfroot helper is available
        _ensure_sf_helper(eng)

        # Determine function signature
        code_stripped = code.strip()

        # Quick block existence check
        try:
            btype = eng.get_param(block_path, "BlockType",
                                  nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
            if str(btype).strip() != "SubSystem":
                return f"'{block_path}' is not a SubSystem block (BlockType={btype})."
        except Exception as e:
            return f"Cannot find block '{block_path}': {e}"

        # If the user provided a full function (starts with "function"),
        # use it as-is.  Otherwise pass only the body — the MATLAB helper
        # (mcp_set_mf_code) will read the existing signature and combine.
        new_script = code_stripped

        # Write code to temp file
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".m", delete=False, encoding="utf-8"
        )
        tmp.write(new_script)
        tmp_path = tmp.name.replace("\\", "/")
        tmp.close()

        # Call MATLAB helper (pure ASCII, no COM encoding risk)
        try:
            eng.eval(
                f"mcp_set_mf_code('{escape_matlab(block_path)}', "
                f"'{escape_matlab(tmp_path)}');",
                nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
            )
        finally:
            _os.unlink(tmp.name)

        _save_model(block_path.split("/")[0])
        return f"Code set on '{block_path}' ({len(code.splitlines())} lines)."

    except Exception as e:
        try:
            eng.eval("clear __mcp_rt __mcp_m __mcp_charts __mcp_sig __mcp_ci;",
                     nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            pass
        return f"Error setting MATLAB Function code: {e}"


@mcp.tool()
def set_model_config(model_name: str, params: str) -> str:
    """Set model-level configuration parameters.

    `params` is a JSON string of key-value pairs, e.g.:
        {"StopTime": "10", "Solver": "ode45"}

    Common parameters: Solver, StopTime, StartTime, MaxStep, AbsTol,
    RelTol, SaveOutput, SaveState.
    """
    try:
        param_dict = json.loads(params)
    except json.JSONDecodeError as e:
        return f"Invalid JSON in params: {e}"

    name = escape_matlab(model_name)
    set_params: list[str] = []
    errors: list[str] = []

    eng = get_engine()

    for key, value in param_dict.items():
        try:
            val_str = str(value)

            # Resolve solver aliases (GUI name → API name)
            if key == "Solver" and _normalize(val_str) in (
                _normalize(k) for k in _SOLVER_ALIASES
            ):
                for alias, canonical in _SOLVER_ALIASES.items():
                    if _normalize(val_str) == _normalize(alias):
                        val_str = canonical
                        break

            # Fuzzy-match enum values for model-level params
            ev = _get_enum_values(eng, model_name, key)
            if ev:
                norm_val = _normalize(val_str)
                matches = [v for v in ev if _normalize(v) == norm_val]
                if len(matches) == 1:
                    val_str = matches[0]
                else:
                    errors.append(
                        f"  {key}: '{value}' is not valid. "
                        f"Allowed: {', '.join(ev)}"
                    )
                    continue

            matlab_eval(
                f"set_param('{name}', '{escape_matlab(key)}', "
                f"'{escape_matlab(val_str)}');"
            )
            set_params.append(f"  {key} = '{val_str}'")
        except Exception as e:
            errors.append(f"  {key}: {e}")

    parts: list[str] = []
    if set_params:
        parts.append(
            f"Set {len(set_params)} parameter(s) on '{model_name}':\n"
            + "\n".join(set_params)
        )
    if errors:
        parts.append(
            f"Failed to set {len(errors)} parameter(s):\n" + "\n".join(errors)
        )

    _save_model(model_name)
    return "\n".join(parts) if parts else "No parameters provided."


def _validate_destination(eng, destination: str) -> str | None:
    """Validate model is loaded and every parent subsystem exists.

    Returns error string or None if valid.
    """
    parts = [p for p in destination.split("/") if p]
    if len(parts) < 2:
        return f"Invalid destination '{destination}': must be 'model/BlockName' or deeper."

    model = parts[0]

    # 1. Check model is loaded
    try:
        loaded = eng.eval(
            f"bdIsLoaded('{escape_matlab(model)}')", nargout=1,
            stdout=io.StringIO(), stderr=io.StringIO(),
        )
        if not bool(loaded):
            return f"Model '{model}' is not loaded."
    except Exception:
        return f"Model '{model}' is not loaded."

    # 2. Check each parent subsystem level (skip last part = block name)
    for i in range(1, len(parts) - 1):
        sub_path = "/".join(parts[: i + 1])
        try:
            eng.get_param(
                sub_path, "Name",
                nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
            )
        except Exception:
            return (
                f"Parent subsystem '{sub_path}' not found — "
                f"full path: {destination}"
            )

    return None


@mcp.tool()
def add_block(destination: str, source: str, params: str = "") -> str:
    """Add a block from the Simulink or powerlib library to a model.

    `destination` is the target path in the model, e.g.: "mymodel/MyGain"

    `source` is a library path. Use `search_library` to find the correct
    path before calling this tool.

    Examples:
        "simulink/Continuous/Transfer Fcn"
        "simulink/Math Operations/Gain"
        "powerlib/Elements/Three-Phase Series RLC Branch"
        "powerlib/Power Electronics/Universal Bridge"
        "powerlib/Sources/Three-Phase Programmable Voltage Source"

    `params` is an optional JSON string of parameter key-value pairs.

    Batch mode: `source` is a JSON array of objects, each with:
        - "name" (required): block name
        - "source" (required): library path
        - "params" (optional): dict of parameter key-value pairs
    In batch mode, `destination` is the model name.

    Validates paths layer-by-layer before calling MATLAB.
    """
    try:
        eng = get_engine()

        # ── Detect mode: batch if source starts with '[' ──
        if source.strip().startswith("["):
            try:
                blocks = json.loads(source)
            except json.JSONDecodeError as e:
                return f"Invalid JSON in source: {e}"

            if not isinstance(blocks, list):
                return "Batch mode: source must be a JSON array."

            model_name = destination
            added: list[str] = []
            errors: list[str] = []

            for block in blocks:
                if not isinstance(block, dict) or "name" not in block or "source" not in block:
                    errors.append(f"Skipping invalid entry: {block}")
                    continue

                block_name = block["name"]
                block_source = block["source"]
                block_params = block.get("params", {})
                dest = f"{model_name}/{block_name}"

                err = _validate_destination(eng, dest)
                if err:
                    errors.append(f"  {block_name}: {err}")
                    continue

                try:
                    src = escape_matlab(block_source)
                    dst = escape_matlab(dest)
                    if block_params:
                        param_args = ""
                        for k, v in block_params.items():
                            param_args += (
                                f", '{escape_matlab(str(k))}', "
                                f"'{escape_matlab(str(v))}'"
                            )
                        matlab_eval(f"add_block('{src}', '{dst}'{param_args});")
                    else:
                        matlab_eval(f"add_block('{src}', '{dst}');")

                    param_str = ""
                    if block_params:
                        param_str = (
                            " ("
                            + ", ".join(f"{k}={v}" for k, v in block_params.items())
                            + ")"
                        )
                    added.append(f"  {block_name}{param_str}")
                except Exception as e:
                    errors.append(f"  {block_name}: {e}")

            out: list[str] = []
            if added:
                out.append(
                    f"Added {len(added)} block(s) to '{model_name}':\n"
                    + "\n".join(added)
                )
            if errors:
                out.append(
                    f"Failed to add {len(errors)} block(s):\n"
                    + "\n".join(errors)
                )

            _save_model(model_name)
            return "\n".join(out) if out else "No blocks provided."

        # ── Single mode ──
        param_dict: dict[str, str] = {}
        if params:
            try:
                param_dict = json.loads(params)
            except json.JSONDecodeError as e:
                return f"Invalid JSON in params: {e}"

        err = _validate_destination(eng, destination)
        if err:
            return f"Error: {err}"

        src = escape_matlab(source)
        dst = escape_matlab(destination)

        if param_dict:
            param_args = ""
            for key, value in param_dict.items():
                param_args += (
                    f", '{escape_matlab(key)}', '{escape_matlab(value)}'"
                )
            matlab_eval(f"add_block('{src}', '{dst}'{param_args});")
        else:
            matlab_eval(f"add_block('{src}', '{dst}');")

        result = f"Added block '{destination}' from '{source}'."
        if param_dict:
            param_list = ", ".join(f"{k}='{v}'" for k, v in param_dict.items())
            result += f" Parameters set: {param_list}."

        _save_model(destination.split("/")[0])
        return result

    except Exception as e:
        return f"Error adding block: {e}"


@mcp.tool()
def delete_block(block_path: str) -> str:
    """Delete a block from a Simulink model.

    Connected lines are removed first via port handle inspection,
    then the block itself is deleted.
    """
    try:
        from simubridge.tools.inspection import _ensure_ports_helper

        eng = get_engine()
        _ensure_ports_helper(eng)

        # All port handle + delete operations inside MATLAB helper
        bp = escape_matlab(block_path)
        matlab_eval(f"mcp_delete_block('{bp}');")

        _save_model(block_path.split("/")[0])
        return f"Deleted block '{block_path}' and its connected lines."

    except Exception as e:
        return f"Error deleting block: {e}"


@mcp.tool()
def delete_line(
    model_name: str,
    src_block: str,
    src_port: int,
    dst_block: str,
    dst_port: int,
    src_port_type: str = "",
    dst_port_type: str = "",
) -> str:
    """Delete a single connection between two ports.

    Args:
        model_name: Name of the Simulink model.
        src_block: Source block name (relative to model).
        src_port: Source port number (1-indexed).
        dst_block: Destination block name.
        dst_port: Destination port number (1-indexed).
        src_port_type: Optional port type ('LConn' or 'RConn') to pin source port type.
        dst_port_type: Optional port type ('LConn' or 'RConn') to pin dest port type.
    """
    try:
        from simubridge.tools.inspection import _ensure_ports_helper

        eng = get_engine()
        _ensure_ports_helper(eng)

        # Strip model_name prefix if already present (avoid double prefix)
        def _rel_path(name: str) -> str:
            prefix = f"{model_name}/"
            if name.startswith(prefix):
                return name[len(prefix):]
            return name

        src_rel = _rel_path(src_block)
        dst_rel = _rel_path(dst_block)
        src_full = escape_matlab(f"{model_name}/{src_rel}")
        dst_full = escape_matlab(f"{model_name}/{dst_rel}")

        result, _, _ = matlab_eval(
            f"mcp_delete_line('{src_full}', {src_port}, '{dst_full}', {dst_port}, "
            f"'{src_port_type}', '{dst_port_type}');",
            nargout=1,
        )

        if float(str(result).strip()) == 1:
            _save_model(model_name)
            return (
                f"Deleted line: '{src_rel}/{src_port}' -> "
                f"'{dst_rel}/{dst_port}' in '{model_name}'."
            )

        # Read error from MATLAB helper
        err_msg = ""
        try:
            err_msg = str(eng.workspace["mcp_delete_line_err"])
        except Exception:
            pass

        detail = f" ({err_msg})" if err_msg else ""
        return (
            f"No line found from '{src_rel}/{src_port}' to "
            f"'{dst_rel}/{dst_port}' in '{model_name}'.{detail}"
        )

    except Exception as e:
        return f"Error deleting line: {e}"


@mcp.tool()
def set_workspace_vars(vars_json: str) -> str:
    """Write variables into the MATLAB base workspace from a JSON dict.

    Essential for setting up simulation base values (S_base, f_g, V_g, etc.)
    before building a model. Values can be numbers, strings, or arrays.

    Example:
        {
            "S_base": 0.532e6,
            "f_g": 50,
            "Vg_n_rms": 433.01,
            "M": 10,
            "D": 100
        }
    """
    try:
        vars_dict = json.loads(vars_json)
    except json.JSONDecodeError as e:
        return f"Invalid JSON: {e}"

    if not isinstance(vars_dict, dict):
        return "vars_json must be a JSON object of key-value pairs."
    return _set_workspace_vars(vars_dict)
