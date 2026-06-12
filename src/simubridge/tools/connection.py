"""Connect blocks — signal and power wiring, unified."""

import io

from simubridge.app import (
    mcp, matlab_eval, escape_matlab, get_engine, matlab_to_float,
)


def _save_model(model_name: str) -> None:
    """Auto-save after every write so the user sees changes in the GUI."""
    try:
        matlab_eval(f"save_system('{escape_matlab(model_name)}');")
    except Exception:
        pass


def _connect_via_handles(model_name: str, src_block: str, src_idx: int,
                         dst_block: str, dst_idx: int,
                         src_type: str = "", dst_type: str = "") -> tuple[bool, str]:
    """Try connecting using LConn/RConn port handles (for SPS blocks).

    Calls MATLAB helper mcp_connect_ports which tries all 7 port-type
    combinations unless src_type / dst_type are specified to pin the
    port type (e.g. 'LConn', 'RConn').

    Returns (success, error_message).
    """
    from simubridge.tools.inspection import _ensure_ports_helper

    eng = get_engine()
    try:
        _ensure_ports_helper(eng)

        src_full = escape_matlab(f"{model_name}/{src_block}")
        dst_full = escape_matlab(f"{model_name}/{dst_block}")

        result, _, _ = matlab_eval(
            f"mcp_connect_ports('{src_full}', {src_idx}, '{dst_full}', {dst_idx}, "
            f"'{src_type}', '{dst_type}');",
            nargout=1,
        )
        res = matlab_to_float(result)
        if res == 1:
            return True, ""
        else:
            try:
                msg = str(eng.workspace["mcp_connect_msg"])
            except Exception:
                msg = "mcp_connect_ports: no valid port-type combination found"
            return False, msg
    except Exception as exc:
        return False, str(exc)


def _try_connect(model_name: str, src_full: str, dst_full: str,
                 src_type: str = "", dst_type: str = "") -> tuple[bool, str]:
    """Try connecting src_full to dst_full via add_line, fall back to handles.

    src_full / dst_full are strings like "Subsys/BlockName/portNumber".
    Automatically determines the common parent subsystem so add_line is
    scoped correctly for nested subsystems.

    Returns (success, error_message).
    """
    # Determine common parent system for correct add_line scoping
    src_block = src_full.rsplit("/", 1)[0]
    dst_block = dst_full.rsplit("/", 1)[0]
    src_port_str = src_full.rsplit("/", 1)[1]
    dst_port_str = dst_full.rsplit("/", 1)[1]

    src_parts = src_block.split("/")
    dst_parts = dst_block.split("/")
    common = 0
    for a, b in zip(src_parts, dst_parts):
        if a == b:
            common += 1
        else:
            break

    if common > 0:
        parent = "/".join(src_parts[:common])
        system = f"{model_name}/{parent}"
        sp = f"{'/'.join(src_parts[common:])}/{src_port_str}" if common < len(src_parts) else src_port_str
        dp = f"{'/'.join(dst_parts[common:])}/{dst_port_str}" if common < len(dst_parts) else dst_port_str
    else:
        system = model_name
        sp = src_full
        dp = dst_full

    name = escape_matlab(system)
    try:
        result, out_str, err_str = matlab_eval(
            f"add_line('{name}', "
            f"'{escape_matlab(sp)}', "
            f"'{escape_matlab(dp)}', "
            f"'autorouting', 'on');"
        )
        err = str(err_str).strip() if err_str else ""
    except Exception as exc:
        err = str(exc)

    if err and ("invalid" in err.lower() or "无效" in err):
        # SPS masked block — fall back to port handles
        parts_src = src_full.rsplit("/", 1)
        parts_dst = dst_full.rsplit("/", 1)
        src_block = parts_src[0] if len(parts_src) == 2 else src_full
        dst_block = parts_dst[0] if len(parts_dst) == 2 else dst_full
        try:
            sp = int(parts_src[1]) if len(parts_src) == 2 else 1
            dp = int(parts_dst[1]) if len(parts_dst) == 2 else 1
        except ValueError:
            sp, dp = 1, 1
        return _connect_via_handles(model_name, src_block, sp, dst_block, dp, src_type, dst_type)
    elif err:
        return False, err
    return True, ""


def _describe_power_ports(model_name: str, block_name: str) -> str:
    """Return a compact summary of LConn/RConn ports like 'LConn×3(2✓ 1✗) RConn×2(1✓ 1✗)'."""
    eng = get_engine()
    try:
        bp = escape_matlab(f"{model_name}/{block_name}")
        code = (
            f"ph = get_param('{bp}', 'PortHandles'); "
            f"parts = {{}}; "
            f"for f = {{'LConn','RConn'}}; "
            f"  ff = f{{1}}; "
            f"  if isfield(ph, ff); "
            f"    n = length(ph.(ff)); "
            f"    if n > 0; "
            f"      c = 0; "
            f"      for i = 1:n; "
            f"        if get_param(ph.(ff)(i), 'Line') > 0; c = c + 1; end; "
            f"      end; "
            f"      u = n - c; "
            f"      parts{{end+1}} = sprintf('%s x%d (%d connected, %d floating)', ff, n, c, u); "
            f"    end; "
            f"  end; "
            f"end; "
            f"if isempty(parts); "
            f"  assignin('base','mcp_pp','(no power ports)'); "
            f"else; "
            f"  assignin('base','mcp_pp', strjoin(parts, ' | ')); "
            f"end;"
        )
        matlab_eval(code, nargout=0)
        try:
            result = str(eng.workspace["mcp_pp"])
        except Exception:
            result = "(unknown)"
        try:
            matlab_eval("clear mcp_pp;", nargout=0)
        except Exception:
            pass
        return result
    except Exception:
        return "(error)"


def _list_floating_power_ports(model_name: str, block_name: str) -> list[str]:
    """Return human-readable labels for LConn/RConn ports with no line."""
    eng = get_engine()
    floating: list[str] = []
    try:
        bp = escape_matlab(f"{model_name}/{block_name}")
        code = (
            f"ph = get_param('{bp}', 'PortHandles'); "
            f"fp = {{}}; "
            f"for f = {{'LConn','RConn'}}; "
            f"  ff = f{{1}}; "
            f"  if isfield(ph, ff); "
            f"    for i = 1:length(ph.(ff)); "
            f"      if get_param(ph.(ff)(i), 'Line') <= 0; "
            f"        fp{{end+1}} = sprintf('%s%d', ff, i); "
            f"      end; "
            f"    end; "
            f"  end; "
            f"end; "
            f"assignin('base', 'mcp_fp', fp);"
        )
        matlab_eval(code, nargout=0)
        try:
            fp = eng.workspace["mcp_fp"]
            if fp:
                for item in fp:
                    floating.append(str(item))
        except Exception:
            pass
        try:
            matlab_eval("clear mcp_fp;", nargout=0)
        except Exception:
            pass
    except Exception:
        pass
    return floating


@mcp.tool()
def connect(
    model_name: str,
    src_block: str,
    dst_block: str,
    src_port: int = 0,
    dst_port: int = 0,
    src_ports: str = "",
    dst_ports: str = "",
    src_port_type: str = "",
    dst_port_type: str = "",
) -> str:
    """Connect two blocks — signal or power, single port or batch.

    Works for any block type (standard Simulink or SPS/powerlib). Supports
    same-block self-connections (src_block == dst_block).

    Single port: give src_port + dst_port
    Batch:        give src_ports="1,2,3" + dst_ports="1,2,3"

    Args:
        model_name: Name of the Simulink model.
        src_block:  Source block name (relative to model, e.g. "Grid").
        dst_block:  Destination block name (can be same as src_block).
        src_port:   Single source port number (use this OR src_ports).
        dst_port:   Single destination port number (use this OR dst_ports).
        src_ports:  Comma-separated source port list, e.g. "1,2,3".
        dst_ports:  Comma-separated destination port list, e.g. "1,2,3".
        src_port_type: Optional port type ('LConn' or 'RConn') to pin source port type.
        dst_port_type: Optional port type ('LConn' or 'RConn') to pin dest port type.
    """
    try:
        # Strip model prefix so src_block/dst_block remain relative to model_name
        def _rel(ref: str) -> str:
            prefix = model_name + "/"
            return ref[len(prefix):] if ref.startswith(prefix) else ref

        src_block = _rel(src_block)
        dst_block = _rel(dst_block)

        # --- resolve port lists ---
        if src_ports:
            src_list = [int(p.strip()) for p in src_ports.split(",")]
        elif src_port > 0:
            src_list = [src_port]
        else:
            return "Provide either src_port (single) or src_ports (batch, e.g. '1,2,3')."

        if dst_ports:
            dst_list = [int(p.strip()) for p in dst_ports.split(",")]
        elif dst_port > 0:
            dst_list = [dst_port]
        else:
            return "Provide either dst_port (single) or dst_ports (batch, e.g. '1,2,3')."

        if len(src_list) != len(dst_list):
            return (
                f"Port count mismatch: {len(src_list)} source vs "
                f"{len(dst_list)} destination. Use src_ports / dst_ports "
                f"to specify matching port pairs."
            )

        # --- port layouts (before connecting) ---
        src_layout = _describe_power_ports(model_name, src_block)
        dst_layout = _describe_power_ports(model_name, dst_block)

        connected = []
        failed = []

        for sp, dp in zip(src_list, dst_list):
            src_full = f"{src_block}/{sp}"
            dst_full = f"{dst_block}/{dp}"
            ok, err = _try_connect(model_name, src_full, dst_full, src_port_type, dst_port_type)
            if ok:
                connected.append(f"{src_full} -> {dst_full}")
            else:
                failed.append(f"{src_full} -> {dst_full} ({err})")

        if failed and not connected:
            return (
                f"Failed to connect all {len(failed)} port(s) in '{model_name}':\n"
                + "\n".join(f"  {f}" for f in failed)
            )

        # --- build result with port layouts ---
        msg_parts = [
            f"Port layouts:",
            f"  {src_block}: {src_layout}",
            f"  {dst_block}: {dst_layout}",
            "",
            f"Connected {len(connected)} port(s) in '{model_name}'.",
        ]
        if connected:
            msg_parts.append("\n".join(f"  {c}" for c in connected))
        if failed:
            msg_parts.append("Failed:\n" + "\n".join(f"  {f}" for f in failed))
        msg = "\n".join(msg_parts)

        # --- audit unconnected power ports on involved blocks ---
        blocks_seen: set[str] = set()
        for blk in (src_block, dst_block):
            if blk in blocks_seen:
                continue
            blocks_seen.add(blk)
            floating = _list_floating_power_ports(model_name, blk)
            if floating:
                msg += (
                    f"\nWarning: '{blk}' has {len(floating)} unconnected "
                    f"power port(s): {', '.join(floating)}"
                )
        _save_model(model_name)
        return msg

    except Exception as e:
        return f"Error connecting: {e}"


