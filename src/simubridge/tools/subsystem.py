"""Subsystem management — create, delete, and navigate subsystem boundaries."""

import io

from simubridge.app import (
    mcp, matlab_eval, escape_matlab, get_engine,
)


def _save_model(model_name: str) -> None:
    """Auto-save after every write so the user sees changes in the GUI."""
    try:
        matlab_eval(f"save_system('{escape_matlab(model_name)}');")
    except Exception:
        pass


@mcp.tool()
def create_subsystem(
    model_name: str,
    block_names: str,
    subsystem_name: str = "",
) -> str:
    """Wrap a list of blocks into a new subsystem with auto Inport/Outport creation.

    Simulink automatically creates Inport and Outport blocks for signals that
    cross the new subsystem boundary.

    Args:
        model_name: Name of the loaded Simulink model.
        block_names: Comma-separated list of block names (relative to model,
                     or full paths). E.g. "Gain1,Sum1,Integrator1".
        subsystem_name: Optional name for the new subsystem. If empty, Simulink
                        assigns a default name like "Subsystem".
    """
    try:
        eng = get_engine()

        blocks = [b.strip() for b in block_names.split(",") if b.strip()]
        if not blocks:
            return "No blocks provided. Supply a comma-separated list of block names."

        esc_name = escape_matlab(model_name)

        # Build full paths: if a block name does not contain '/', prefix with model name
        full_paths = []
        for b in blocks:
            if "/" in b:
                full_paths.append(b)
            else:
                full_paths.append(f"{model_name}/{b}")

        # Convert block paths to handles via get_param
        handle_strs = []
        for p in full_paths:
            handle_strs.append(
                f"get_param('{escape_matlab(p)}','Handle')"
            )
        handle_array = "[" + " ".join(handle_strs) + "]"

        # Record existing subsystems BEFORE creation
        before_ss = set(eng.find_system(
            model_name, "SearchDepth", 1, "BlockType", "SubSystem",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        ))

        # Create the subsystem (may not return a value)
        matlab_eval(f"Simulink.BlockDiagram.createSubsystem({handle_array});")

        # Find the newly created subsystem by diff
        new_ss_path = ""
        after_ss = set(eng.find_system(
            model_name, "SearchDepth", 1, "BlockType", "SubSystem",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        ))
        diff = after_ss - before_ss
        if len(diff) == 1:
            new_ss_path = list(diff)[0]

        # If subsystem_name is provided, rename
        if subsystem_name and new_ss_path:
            matlab_eval(
                f"set_param('{escape_matlab(new_ss_path)}', 'Name', "
                f"'{escape_matlab(subsystem_name)}');"
            )
            parts = new_ss_path.rsplit("/", 1)
            if len(parts) == 2:
                new_ss_path = f"{parts[0]}/{subsystem_name}"

        summary = f"Created subsystem from {len(blocks)} block(s)."
        if new_ss_path:
            summary += f"\nSubsystem path: {new_ss_path}"

        # List new subsystem contents
        if new_ss_path:
            try:
                content, _, _ = matlab_eval(
                    f"strjoin(find_system('{escape_matlab(new_ss_path)}', "
                    f"'SearchDepth', 1), newline);",
                    nargout=1,
                )
                lines = [
                    b for b in str(content).splitlines()
                    if b and b != new_ss_path
                ]
                if lines:
                    summary += f"\nContents ({len(lines)} block(s)):"
                    for ln in lines:
                        summary += f"\n  {ln}"
            except Exception:
                pass

        _save_model(model_name.split("/")[0])
        return summary

    except Exception as e:
        return f"Error creating subsystem: {e}"


@mcp.tool()
def expand_subsystem(
    subsystem_path: str,
) -> str:
    """Expand (flatten) a subsystem into its parent diagram.

    All blocks and lines inside the subsystem are moved up one level.
    Inports and Outports on the subsystem boundary are removed, and
    connections broken at the boundary are re-wired where possible.

    Args:
        subsystem_path: Full path to the subsystem block to flatten.
    """
    try:
        bp = escape_matlab(subsystem_path)
        # Get parent before expanding
        parent, _, _ = matlab_eval(
            f"get_param('{bp}', 'Parent');",
            nargout=1,
        )
        parent_name = str(parent).strip()

        matlab_eval(
            f"Simulink.BlockDiagram.expandSubsystem('{bp}');"
        )

        _save_model(subsystem_path.split("/")[0])
        return (
            f"Expanded subsystem '{subsystem_path}'.  "
            f"All blocks moved to parent '{parent_name}'."
        )

    except Exception as e:
        return f"Error expanding subsystem: {e}"


@mcp.tool()
def add_subsystem_port(
    subsystem_path: str,
    port_type: str = "Inport",
    port_number: int = 1,
    port_name: str = "",
) -> str:
    """Add an Inport or Outport block to the inside of a subsystem.

    This is useful when you need to expose an additional signal to/from
    a subsystem after it was created.  The matching port appears on the
    subsystem block automatically.

    Args:
        subsystem_path: Full path to the subsystem (e.g. 'model/Subsys').
        port_type: 'Inport' or 'Outport'.
        port_number: Port position (1-indexed).  New port is added before
                     the existing port at this position.
        port_name: Optional label for the port block.
    """
    try:
        bp = escape_matlab(subsystem_path)
        eng = get_engine()

        blk_type = "simulink/Sources/In1" if port_type == "Inport" else "simulink/Sinks/Out1"

        # Find existing ports of this type
        ports = eng.find_system(
            subsystem_path, "SearchDepth", 1, "BlockType", port_type,
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        if ports is None:
            ports = []
        num_existing = len(ports)

        # Clamp port_number
        insert_at = max(1, min(port_number, num_existing + 1))

        # Add the port with a temp name first
        new_name = port_name if port_name else f"{port_type}{insert_at}"
        matlab_eval(f"add_block('{blk_type}', '{bp}/{new_name}');")

        # If inserted before the end, renumber existing ports
        if insert_at <= num_existing:
            # Shift ports at insert_at .. num_existing up by 1
            for idx in range(num_existing, insert_at - 1, -1):
                old_path = ports[idx - 1]
                matlab_eval(
                    f"set_param('{escape_matlab(old_path)}', 'Name', "
                    f"'{port_type}{idx + 1}');"
                )

        # List updated ports to confirm
        updated, _, _ = matlab_eval(
            f"length(find_system('{bp}', 'SearchDepth', 1, 'BlockType', '{port_type}'));",
            nargout=1,
        )
        total = int(float(str(updated).strip()))
        _save_model(subsystem_path.split("/")[0])
        return (
            f"Added {port_type} '{new_name}' at position {insert_at} "
            f"in '{subsystem_path}' ({total} {port_type}(s) total)."
        )

    except Exception as e:
        return f"Error adding subsystem port: {e}"


@mcp.tool()
def remove_subsystem_port(
    subsystem_path: str,
    port_type: str,
    port_number: int,
) -> str:
    """Remove an Inport or Outport from inside a subsystem.

    The corresponding external port on the subsystem block is also removed.
    Connected lines are deleted first.

    Args:
        subsystem_path: Full path to the subsystem.
        port_type: 'Inport' or 'Outport'.
        port_number: 1-indexed port number to remove.
    """
    try:
        eng = get_engine()

        # Find port blocks via direct API
        ports = eng.find_system(
            subsystem_path, "SearchDepth", 1, "BlockType", port_type,
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        if not ports or port_number > len(ports):
            return f"Port {port_number} ({port_type}) not found in '{subsystem_path}'."

        port_path = ports[port_number - 1]

        # Delete via short eval
        eng.eval(f"delete_block('{escape_matlab(port_path)}');",
                 nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

        _save_model(subsystem_path.split("/")[0])
        return f"Removed {port_type} #{port_number} ('{port_path}') from '{subsystem_path}'."

    except Exception as e:
        matlab_eval("clear __mcp_blks;")
        return f"Error removing subsystem port: {e}"
