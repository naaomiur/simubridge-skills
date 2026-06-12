"""Model inspection — list blocks, read parameters, read configuration."""

import io
import re
import zipfile
import os as _os

from simubridge.app import (
    mcp, matlab_eval, escape_matlab, get_engine,
)


_COMMON_LIBRARIES = [
    # Base
    "simulink",
    # Power systems
    "powerlib", "powerlib_extras", "powerlib_meascontrol",
    # Embedded / C2000
    "c2000lib", "c2803xlib",
    # Simscape
    "simscape", "sps_lib", "elec_lib", "fl_lib", "sm_lib", "sdl_lib",
    # Control & MPC
    "mpclib", "rllib", "nnetlib",
    # Autonomous & robotics
    "autolib", "drivinglib", "uavlib", "roslib", "sl3dlib",
    # Comms / radar / phased array
    "phasedlib", "radarlib", "satcomlib",
    # Vision / HDL
    "visionlib", "visionhdllib", "whdllib",
    # Vehicle
    "canlib",
    # Stateflow
    "sflib",
    # Real-time & PLC
    "slrtlib", "sldrtlib", "plclib",
    # DDS / AUTOSAR
    "ddslib", "autosarlib",
]


def _parse_slx_tree(slx_path: str) -> dict[str, list[str]]:
    """Parse an SPS-style .slx library and return {SubSystemName: [block_paths]}.

    Walks system_root.xml → _rels → child system XMLs recursively.
    SubSystem internal names are used as-is; the caller maps them to
    display names if needed.
    """
    tree: dict[str, list[str]] = {}

    def _read_xml(z: zipfile.ZipFile, name: str) -> str:
        return z.read(name).decode("utf-8", errors="replace")

    def _rels_for(z: zipfile.ZipFile, sys_xml_name: str) -> dict[str, str]:
        """Return {SID: target_xml_filename} from the _rels file.

        Targets in _rels are relative to the directory of sys_xml_name;
        we resolve them to full zip-internal paths.
        """
        dirname = _os.path.dirname(sys_xml_name)
        basename = _os.path.basename(sys_xml_name)
        rels_name = f"{dirname}/_rels/{basename}.rels"
        sid_to_sys: dict[str, str] = {}
        try:
            rels_xml = _read_xml(z, rels_name)
            for m in re.finditer(
                r'<Relationship\s+Id="system_(\d+)"\s+Target="([^"]+)"',
                rels_xml,
            ):
                target = f"{dirname}/{m.group(2)}"
                sid_to_sys[m.group(1)] = target
        except Exception:
            pass
        return sid_to_sys

    def _walk(z: zipfile.ZipFile, sys_xml_name: str, prefix: str) -> None:
        if sys_xml_name not in set(z.namelist()):
            return
        xml = _read_xml(z, sys_xml_name)
        sid_to_sys = _rels_for(z, sys_xml_name)

        for m in re.finditer(
            r'<Block\s+BlockType="(SubSystem|Reference)"\s+Name="([^"]+)"\s+SID="(\d+)"',
            xml,
        ):
            block_type = m.group(1)
            block_name = m.group(2).replace("&#xA;", "\n")
            block_sid = m.group(3)
            full_path = f"{prefix}/{block_name}".lstrip("/")

            if block_type == "Reference":
                if prefix not in tree:
                    tree[prefix] = []
                tree[prefix].append(full_path)
            elif block_type == "SubSystem" and block_sid in sid_to_sys:
                _walk(z, sid_to_sys[block_sid], full_path)

    try:
        with zipfile.ZipFile(slx_path, "r") as z:
            _walk(z, "simulink/systems/system_root.xml", "")
    except Exception:
        pass
    return tree


# Mapping from sps_lib.slx internal SubSystem names to powerlib display names.
# Needed because powerlib.slx SubSystems are thin links into sps_lib.slx,
# and the internal names differ from user-facing names.
_SPS_NAME_MAP: dict[str, str] = {
    "Sources": "Electrical Sources",
    "Passives": "Elements",
    "Power Grid Elements": "Interface Elements",
    "Electrical Machines": "Machines",
    "Sensors and Measurements": "Measurements",
    "Power Electronics": "Power Electronics",
    "Control": "Control",
    "Utilities": "Utilities",
}


def _extract_key_phrases(kw: str) -> list[str]:
    """Split a long keyword into candidate key phrases for fallback search."""
    tokens = re.split(r'[\s&/,]+', kw.strip().lower())
    tokens = [t for t in tokens if len(t) > 2]
    if not tokens:
        return []
    phrases: list[str] = []
    seen: set[str] = set()
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            bg = f"{tokens[i]} {tokens[i+1]}"
            if bg not in seen:
                phrases.append(bg)
                seen.add(bg)
    if len(tokens) >= 3:
        for i in range(len(tokens) - 2):
            tg = f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}"
            if tg not in seen:
                phrases.append(tg)
                seen.add(tg)
    return phrases


def _validate_lib_path(eng, path: str) -> bool:
    """Check that a library block path actually resolves via get_param."""
    try:
        eng.get_param(path, "BlockType",
                      nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        return True
    except Exception:
        return False


def _search_via_xml(lib_name: str, keyword: str, eng) -> list[str]:
    """Search a library by parsing its underlying .slx file directly.

    For SPS libraries (powerlib etc.), the .slx returned by get_param is a
    thin wrapper whose SubSystems link into sps_lib.slx.  We locate the real
    library file (sps_lib.slx) and return ``sps_lib/…`` paths that are
    universal — they work with ``add_block`` regardless of which wrapper
    library they are accessed from.

    Every returned path is validated with ``get_param(path, 'BlockType')``
    before inclusion.
    """
    kw = keyword.lower()
    matches: list[str] = []

    # Ensure library is loaded so FileName is readable
    try:
        eng.eval(
            f"load_system('{escape_matlab(lib_name)}');",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )
    except Exception:
        pass

    try:
        wrapper_path = str(
            eng.get_param(
                lib_name, "FileName",
                nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
            )
        ).strip()
    except Exception:
        return matches

    if not wrapper_path or not _os.path.exists(wrapper_path):
        return matches

    if not wrapper_path.lower().endswith(".slx"):
        return matches

    wrapper_dir = _os.path.dirname(wrapper_path)

    # The real SPS blocks live in sps_lib.slx, in a sibling "library" directory
    real_lib = _os.path.normpath(
        _os.path.join(wrapper_dir, "..", "library", "sps_lib.slx")
    )
    is_sps = _os.path.exists(real_lib)
    if not is_sps:
        real_lib = wrapper_path
    else:
        # sps_lib must be loaded for get_param validation to work
        try:
            eng.eval("load_system('sps_lib');",
                     nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            pass

    tree = _parse_slx_tree(real_lib)

    for block_paths in tree.values():
        for bp in block_paths:
            # Match keyword against a display-friendly version (newlines → spaces).
            # The actual path preserves newline characters because add_block needs them.
            if re.sub(r'\s+', ' ', kw) not in re.sub(r'\s+', ' ', bp.lower()):
                continue

            # Build two candidate paths and keep the first one that validates.
            # sps_lib paths are universal for SPS blocks.
            # wrapper-lib paths preserve the original library name for
            # non-SPS libraries (fallback case).
            candidates: list[str] = []
            if is_sps:
                candidates.append(f"sps_lib/{bp}")
            candidates.append(f"{lib_name}/{bp}")

            kept = None
            for cand in candidates:
                if _validate_lib_path(eng, cand):
                    kept = cand
                    break

            if kept is not None and kept not in matches:
                matches.append(kept)

    return matches


def _do_search(keyword: str, lib_list: list[str], eng, search_depth: int) -> dict[str, list[str]]:
    """Run a single keyword search across libraries. Returns {lib: [paths]}."""
    kw = keyword.lower()
    lib_matches: dict[str, list[str]] = {}
    seen: set[str] = set()

    for lib in lib_list:
        xml_results = _search_via_xml(lib, keyword, eng)
        if xml_results:
            for path in xml_results:
                if path not in seen:
                    seen.add(path)
                    group = "sps_lib" if path.startswith("sps_lib/") else lib
                    lib_matches.setdefault(group, []).append(path)
            continue

        try:
            eng.eval(f"load_system('{escape_matlab(lib)}');",
                     nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            pass

        try:
            top_blocks = eng.find_system(
                lib, "SearchDepth", search_depth,
                nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
            )
            for b in top_blocks:
                if b != lib and re.sub(r'\s+', ' ', kw) in re.sub(r'\s+', ' ', str(b).lower()):
                    if b not in seen:
                        seen.add(b)
                        lib_matches.setdefault(lib, []).append(b)
        except Exception:
            pass

    return lib_matches


@mcp.tool()
def search_library(keyword: str, libraries: str = "", search_depth: int = 5) -> str:
    """Search across multiple Simulink libraries for blocks matching *keyword*.

    Two-stage search:
    1. Full keyword match (case-insensitive, whitespace-normalized substring).
    2. If no results: extract key phrases (bigrams, trigrams, long words)
       from the keyword and search with each — results are merged.

    Args:
        keyword: Case-insensitive substring to match in block paths.
        libraries: Comma-separated list of libraries to search (default: all common).
        search_depth: How deep to search (default 5 for deep search).

    Returns:
        Matching block paths with library source and BlockType.
    """
    try:
        eng = get_engine()

        if libraries:
            lib_list = [lib.strip() for lib in libraries.split(",") if lib.strip()]
        else:
            lib_list = list(_COMMON_LIBRARIES)

        all_lib_matches: dict[str, list[str]] = {}
        all_seen: set[str] = set()

        def _collect(matches: dict[str, list[str]]) -> bool:
            added = False
            for lib, paths in matches.items():
                for p in paths:
                    if p not in all_seen:
                        all_seen.add(p)
                        all_lib_matches.setdefault(lib, []).append(p)
                        added = True
            return added

        # Stage 1: Full keyword search
        _collect(_do_search(keyword, lib_list, eng, search_depth))

        # Stage 2: Fallback — key phrases from the original keyword
        if not all_lib_matches:
            for phrase in _extract_key_phrases(keyword):
                _collect(_do_search(phrase, lib_list, eng, search_depth))

        if not all_lib_matches:
            return f"No blocks matching '{keyword}' found in any library."

        all_matches = []
        for paths in all_lib_matches.values():
            all_matches.extend(paths)

        lines = [f"Found {len(all_matches)} block(s) matching '{keyword}':"]
        for lib in sorted(all_lib_matches.keys()):
            lines.append(f"\n  [{lib}]")
            for path in sorted(set(all_lib_matches[lib])):
                try:
                    bt = eng.get_param(path, "BlockType",
                                       nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
                except Exception:
                    bt = "?"
                lines.append(f"    {path}  [{bt}]")

        return "\n".join(lines)

    except Exception as e:
        return f"Error searching libraries: {e}"


@mcp.tool()
def model_audit(model_name: str, depth: int = 5) -> str:
    """Read complete model topology: blocks, signal/power/implicit connections.

    Shows all four connection types:
    - Signal lines (visible wires at every subsystem level)
    - Goto/From implicit connections (by tag name)
    - Data Store implicit connections (by variable name)
    - Power connections (SPS LConn/RConn, only present in power models)

    Args:
        model_name: Model or subsystem path (e.g. 'mymodel' or 'mymodel/Sub').
        depth: Hierarchy depth to read (default 2).
    """
    try:
        eng = get_engine()

        blocks = eng.find_system(
            model_name, "SearchDepth", float(depth),
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        model_depth = model_name.count("/")
        lines_out = [
            f"Topology of '{model_name}' (depth={depth}):",
            "",
            f"Blocks ({len(blocks)}):",
        ]

        # Collect subsystems while building block list (reuse bt from loop)
        subsystems: list[str] = []
        for path in blocks:
            path_str = str(path)
            try:
                bt = str(eng.get_param(
                    path_str, "BlockType",
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                ))
            except Exception:
                bt = "unknown"
            indent = "  " * (path_str.count("/") - model_depth)
            display = path_str.replace("\n", " ").replace("\r", "")
            lines_out.append(f"{indent}{display}  ({bt})")
            rel_depth = path_str.count("/") - model_depth
            if bt == "SubSystem" and path_str != model_name and rel_depth < depth:
                subsystems.append(path_str)

        # --- Signal connections: root + all subsystems within depth ---
        for sys in [model_name] + subsystems:
            try:
                conn_lines = _read_connections(sys)
                if conn_lines:
                    lines_out.append("")
                    lines_out.append(f"Signal Connections in '{sys}':")
                    lines_out.extend(conn_lines)
            except Exception:
                pass

        # --- Goto/From implicit connections ---
        try:
            goto_lines = _read_goto_from(model_name, depth)
            if goto_lines:
                lines_out.append("")
                lines_out.append("Goto/From Connections:")
                lines_out.extend(goto_lines)
        except Exception:
            pass

        # --- Data Store implicit connections ---
        try:
            ds_lines = _read_data_stores(model_name, depth)
            if ds_lines:
                lines_out.append("")
                lines_out.append("Data Store Connections:")
                lines_out.extend(ds_lines)
        except Exception:
            pass

        # --- Power connections (SPS only) ---
        try:
            pw_lines = _read_power_connections(model_name, depth)
            if pw_lines:
                lines_out.append("")
                lines_out.append("Power Connections:")
                lines_out.extend(pw_lines)
        except Exception:
            pass

        # --- Unconnected ports ---
        try:
            unconn: list[str] = []
            sp = _run_signal_audit(model_name, depth)
            if sp.get("ok"):
                for blk in sp.get("blk_list", []):
                    for s in sp.get("status", {}).get(blk, []):
                        if "UNCONNECTED" in s or "DANGLING" in s:
                            unconn.append(f"  [{blk}] {s}")
            pw = _run_power_audit(model_name, depth)
            if pw.get("ok"):
                for blk in pw.get("blk_list", []):
                    for s in pw.get("status", {}).get(blk, []):
                        if "UNCONNECTED" in s or "DANGLING" in s:
                            unconn.append(f"  [{blk}] {s}")
            if unconn:
                lines_out.append("")
                lines_out.append("Unconnected Ports:")
                lines_out.extend(unconn)
        except Exception:
            pass

        return "\n".join(lines_out)
    except Exception as e:
        return f"Error reading model topology: {e}"


def _read_connections(sys_name: str) -> list[str]:
    """Return formatted connection strings for a system's top-level lines."""
    eng = get_engine()
    # SrcPort/DstPort in the Lines struct are already char port numbers — use directly.
    # Only SrcBlock/DstBlock are handles that need get_param(...,'Name').
    matlab_eval(
        f"mcL = get_param('{escape_matlab(sys_name)}', 'Lines');"
        f"mcOut = {{}};"
        f"for mcI = 1:length(mcL);"
        f"  try;"
        f"  mcSb = get_param(mcL(mcI).SrcBlock, 'Name');"
        f"  mcSp = mcL(mcI).SrcPort;"
        f"  mcSig = mcL(mcI).Name;"
        f"  mcDbs = mcL(mcI).DstBlock;"
        f"  mcDps = mcL(mcI).DstPort;"
        f"  for mcJ = 1:length(mcDbs);"
        f"    mcDn = get_param(mcDbs(mcJ), 'Name');"
        f"    mcDp = mcDps(mcJ);"
        f"    if isempty(mcSig);"
        f"      mcOut{{end+1}} = [mcSb '|' mcSp '|' mcDn '|' mcDp];"
        f"    else;"
        f"      mcOut{{end+1}} = [mcSb '|' mcSp '|' mcDn '|' mcDp '|' mcSig];"
        f"    end;"
        f"  end;"
        f"  catch; end;"
        f"end;"
        f"assignin('base', 'mcResult', mcOut);",
        nargout=0,
    )
    result: list[str] = []
    try:
        raw = eng.workspace["mcResult"]
        for item in raw:
            parts = str(item).split("|")
            if len(parts) >= 4:
                sig = parts[4] if len(parts) > 4 else ""
                src = parts[0].replace("\n", " ").replace("\r", "")
                dst = parts[2].replace("\n", " ").replace("\r", "")
                arrow = f"  {src}/{parts[1]} -> {dst}/{parts[3]}"
                result.append(f"{arrow}  [{sig}]" if sig else arrow)
    except Exception:
        pass
    try:
        matlab_eval(
            "clear mcL mcOut mcI mcSb mcSp mcSig mcDbs mcDps mcJ mcDn mcDp mcResult;",
            nargout=0,
        )
    except Exception:
        pass
    return result


def _rel_path(full: str, model_name: str) -> str:
    """Return path relative to model root, with newlines sanitized."""
    prefix = model_name + "/"
    s = full[len(prefix):] if full.startswith(prefix) else full
    return s.replace("\n", " ").replace("\r", "")


def _read_goto_from(model_name: str, depth: int) -> list[str]:
    """Return Goto→From implicit connection strings."""
    eng = get_engine()
    result: list[str] = []
    try:
        gotos = eng.find_system(
            model_name, "SearchDepth", float(depth), "BlockType", "Goto",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        seen_tags: set[str] = set()
        for goto in gotos:
            goto_str = str(goto)
            try:
                tag = str(eng.get_param(
                    goto_str, "GotoTag",
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                ))
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)
                froms = eng.find_system(
                    model_name, "SearchDepth", float(depth),
                    "BlockType", "From", "GotoTag", tag,
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                )
                goto_name = _rel_path(goto_str, model_name)
                from_names = [_rel_path(str(f), model_name) for f in froms]
                if from_names:
                    result.append(f"  [{tag}] {goto_name} -> {', '.join(from_names)}")
                else:
                    result.append(f"  [{tag}] {goto_name} -> (no From)")
            except Exception:
                pass
    except Exception:
        pass
    return result


def _read_data_stores(model_name: str, depth: int) -> list[str]:
    """Return Data Store Memory/Read/Write implicit connection strings."""
    eng = get_engine()
    result: list[str] = []
    try:
        dsms = eng.find_system(
            model_name, "SearchDepth", float(depth), "BlockType", "DataStoreMemory",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        )
        for dsm in dsms:
            dsm_str = str(dsm)
            try:
                name = str(eng.get_param(
                    dsm_str, "DataStoreName",
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                ))
                writers = eng.find_system(
                    model_name, "SearchDepth", float(depth),
                    "BlockType", "DataStoreWrite", "DataStoreName", name,
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                )
                readers = eng.find_system(
                    model_name, "SearchDepth", float(depth),
                    "BlockType", "DataStoreRead", "DataStoreName", name,
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
                )
                dsm_name = _rel_path(dsm_str, model_name)
                w_names = [_rel_path(str(w), model_name) for w in writers]
                r_names = [_rel_path(str(r), model_name) for r in readers]
                line = f"  [{name}] Memory:{dsm_name}"
                if w_names:
                    line += f"  Write:{','.join(w_names)}"
                if r_names:
                    line += f"  Read:{','.join(r_names)}"
                result.append(line)
            except Exception:
                pass
    except Exception:
        pass
    return result


def _read_power_connections(model_name: str, depth: int) -> list[str]:
    """Return SPS power connection strings using audit infrastructure."""
    try:
        data = _run_power_audit(model_name, depth)
        if not data.get("ok") or not data.get("blk_list"):
            return []
        result: list[str] = []
        for blk in data["blk_list"]:
            blk_str = str(blk).strip()
            status_lines = data["status"].get(blk_str, [])
            for s in status_lines:
                result.append(f"  [{blk_str}] {str(s).strip()}")
        return result
    except Exception:
        return []


def _read_block_params_dict(block_path: str, include_prompts: bool = False) -> dict[str, str]:
    """Read all parameters from a block into {name: value} dict.

    Handles both DialogParameters (standard blocks) and MaskNames/MaskValues
    fallback (SPS/powerlib linked-library masked blocks).

    When *include_prompts* is True (for SPS masked blocks),
    appends ``; "PromptText"`` to the value string for each parameter that
    has a MaskPrompt.
    """
    eng = get_engine()
    dp = eng.get_param(block_path, "DialogParameters",
                       nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
    param_names = list(dp.keys()) if dp and hasattr(dp, 'keys') else []

    result: dict[str, str] = {}
    if param_names:
        for name in param_names:
            try:
                val = str(eng.get_param(
                    block_path, name,
                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO()))
                result[name] = val
            except Exception:
                pass
        if not include_prompts:
            return result
        # Try to enrich with MaskPrompts
        _append_mask_prompts(block_path, result)
        return result

    # Fallback: SPS blocks store params in MaskNames/MaskValues
    try:
        mask_names = eng.get_param(
            block_path, "MaskNames",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_vals = eng.get_param(
            block_path, "MaskValues",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        names = (list(mask_names)
                 if mask_names and hasattr(mask_names, "__iter__")
                 else [])
        vals = (list(mask_vals)
                if mask_vals and hasattr(mask_vals, "__iter__")
                else [])
        for i in range(min(len(names), len(vals))):
            result[str(names[i])] = str(vals[i])
        if include_prompts and result:
            _append_mask_prompts(block_path, result)
    except Exception:
        pass

    return result


def _append_mask_prompts(block_path: str, params: dict[str, str]) -> None:
    """Read MaskPrompts / MaskStyles and append prompt text to param values."""
    eng = get_engine()
    try:
        mask_names = eng.get_param(
            block_path, "MaskNames",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_prompts = eng.get_param(
            block_path, "MaskPrompts",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_styles = eng.get_param(
            block_path, "MaskStyles",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        names = (list(mask_names)
                 if mask_names and hasattr(mask_names, "__iter__")
                 else [])
        prompts = (list(mask_prompts)
                   if mask_prompts and hasattr(mask_prompts, "__iter__")
                   else [])
        styles = (list(mask_styles)
                  if mask_styles and hasattr(mask_styles, "__iter__")
                  else [])
        for i, name in enumerate(names):
            name = str(name)
            if name not in params:
                continue
            parts = [params[name]]
            if i < len(styles) and str(styles[i]):
                parts.append(f"[{styles[i]}]")
            if i < len(prompts) and str(prompts[i]):
                parts.append(f'"{str(prompts[i])}"')
            params[name] = "  ;  ".join(parts)
    except Exception:
        pass


def _get_mask_meta(block_path: str) -> dict[str, dict[str, str]]:
    """Read full mask metadata for every parameter.

    Returns {param_name: {value, prompt, style, visible, enabled}}.
    """
    eng = get_engine()
    result: dict[str, dict[str, str]] = {}
    try:
        mask_names = eng.get_param(
            block_path, "MaskNames",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_vals = eng.get_param(
            block_path, "MaskValues",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_prompts = eng.get_param(
            block_path, "MaskPrompts",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_styles = eng.get_param(
            block_path, "MaskStyles",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_vis = eng.get_param(
            block_path, "MaskVisibilities",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        mask_en = eng.get_param(
            block_path, "MaskEnables",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
        names = (list(mask_names)
                 if mask_names and hasattr(mask_names, "__iter__")
                 else [])
        vals = (list(mask_vals)
                if mask_vals and hasattr(mask_vals, "__iter__")
                else [])
        prompts = (list(mask_prompts)
                   if mask_prompts and hasattr(mask_prompts, "__iter__")
                   else [])
        styles = (list(mask_styles)
                  if mask_styles and hasattr(mask_styles, "__iter__")
                  else [])
        vis = (list(mask_vis)
               if mask_vis and hasattr(mask_vis, "__iter__")
               else [])
        en = (list(mask_en)
              if mask_en and hasattr(mask_en, "__iter__")
              else [])
        for i in range(len(names)):
            meta: dict[str, str] = {}
            meta["value"] = str(vals[i]) if i < len(vals) else ""
            meta["prompt"] = str(prompts[i]) if i < len(prompts) else ""
            meta["style"] = str(styles[i]) if i < len(styles) else ""
            meta["visible"] = str(vis[i]) if i < len(vis) else ""
            meta["enabled"] = str(en[i]) if i < len(en) else ""
            result[str(names[i])] = meta
    except Exception:
        pass
    return result


@mcp.tool()
def get_block_params(block_path: str) -> str:
    """Get all dialog parameters of a Simulink block.

    For masked blocks, shows MaskType and enriches each parameter with its
    prompt label, control style, and visibility/enable flags (HIDDEN, DISABLED).

    Args:
        block_path: Full block path (e.g. 'mymodel/Gain1').
    """
    try:
        eng = get_engine()

        # — MaskType —
        mask_type = ""
        try:
            mt = str(eng.get_param(
                block_path, "MaskType",
                nargout=1, stdout=io.StringIO(), stderr=io.StringIO()))
            if mt and mt.lower() != "none":
                mask_type = f", MaskType: {mt}"
        except Exception:
            pass

        # — Full metadata path —
        meta = _get_mask_meta(block_path)
        if meta:
            lines: list[str] = []
            lines.append(
                f"Parameters for '{block_path}' ({len(meta)} params{mask_type}):\n"
            )
            for name, info in meta.items():
                flags: list[str] = []
                if info.get("style"):
                    flags.append(info["style"])
                vis = info.get("visible", "")
                if vis and vis.lower() in ("off", "0"):
                    flags.append("HIDDEN")
                ena = info.get("enabled", "")
                if ena and ena.lower() in ("off", "0"):
                    flags.append("DISABLED")
                flag_str = f"  [{', '.join(flags)}]" if flags else ""
                prompt = info.get("prompt", "")
                prompt_str = f'  "{prompt}"' if prompt else ""
                lines.append(f"  {name} = {info.get('value', '')}{flag_str}{prompt_str}")
            return "\n".join(lines)

        # Fallback: no mask meta, use DialogParameters with prompts
        params = _read_block_params_dict(block_path, include_prompts=True)
        if not params:
            return f"No dialog parameters found for '{block_path}'."

        lines = []
        lines.append(
            f"Parameters for '{block_path}' ({len(params)} params{mask_type}):\n"
        )
        for name, val in params.items():
            lines.append(f"  {name} = {val}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error getting block parameters: {e}"


_PORTS_HELPER = None  # cached path to ports helper .m file


def _ensure_ports_helper(eng) -> str:
    """Create a MATLAB .m helper that inspects PortHandles.

    All PortHandles access stays inside MATLAB, avoiding COM encoding
    issues when returning the struct across the Python boundary.

    Uses a fixed temp file (always overwritten) so MATLAB path doesn't
    accumulate stale versions.
    """
    import os as _os
    import atexit

    d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_ports_helper_")
    _os.makedirs(d, exist_ok=True)
    p = _os.path.join(d, "mcp_get_ports.m").replace("\\", "/")

    helper_code = r"""function mcp_get_ports(block_path)
    try
        ph = get_param(block_path, 'PortHandles');
        p = get_param(block_path, 'Ports');
        assignin('base', 'mcp_In', double(p(1)));
        if length(p) >= 2
            assignin('base', 'mcp_Out', double(p(2)));
        else
            assignin('base', 'mcp_Out', 0);
        end
        fields = {'Inport', 'Outport', 'Enable', 'Trigger', 'LConn', 'RConn'};
        for i = 1:length(fields)
            try
                vals = ph.(fields{i});
                assignin('base', ['mcp_' fields{i} '_vals'], double(vals));
                assignin('base', ['mcp_' fields{i}], double(length(vals)));
            catch
                assignin('base', ['mcp_' fields{i}], 0);
            end
        end
        % Port names from internal Inport/Outport blocks (SubSystems)
        try
            in_blks = find_system(block_path, 'SearchDepth', 1, ...
                                  'LookUnderMasks', 'all', 'FollowLinks', 'on', ...
                                  'BlockType', 'Inport');
            in_names = cell(1, length(in_blks));
            for j = 1:length(in_blks)
                in_names{j} = get_param(in_blks{j}, 'Name');
            end
            assignin('base', 'mcp_Inport_names', in_names);
        catch
            assignin('base', 'mcp_Inport_names', {});
        end
        try
            out_blks = find_system(block_path, 'SearchDepth', 1, ...
                                   'LookUnderMasks', 'all', 'FollowLinks', 'on', ...
                                   'BlockType', 'Outport');
            out_names = cell(1, length(out_blks));
            for j = 1:length(out_blks)
                out_names{j} = get_param(out_blks{j}, 'Name');
            end
            assignin('base', 'mcp_Outport_names', out_names);
        catch
            assignin('base', 'mcp_Outport_names', {});
        end

        assignin('base', 'mcp_ports_ok', 1);
    catch ME
        assignin('base', 'mcp_ports_ok', 0);
        assignin('base', 'mcp_ports_err', ME.message);
    end
end
"""
    # Only write if changed (avoid unnecessary filesystem noise)
    current = ""
    try:
        with open(p, "r", encoding="utf-8") as f:
            current = f.read()
    except Exception:
        pass
    if current != helper_code:
        with open(p, "w", encoding="utf-8") as f:
            f.write(helper_code)

    eng.eval(f"addpath('{d.replace(chr(92), '/')}'); clear('mcp_get_ports');",
             nargout=0, stdout=io.StringIO(), stderr=io.StringIO())

    return d


def _get_single_block_ports(block_path: str) -> str:
    """Return port layout for one block (internal helper)."""
    try:
        bp = escape_matlab(block_path)
        lines = [f"Ports for '{block_path}':"]

        # Call MATLAB helper to get all port info (now includes port names)
        _ensure_ports_helper(get_engine())
        out = io.StringIO()
        err = io.StringIO()
        get_engine().eval(
            f"mcp_get_ports('{bp}');",
            nargout=0, stdout=out, stderr=err,
        )
        try:
            ok_val = float(get_engine().workspace["mcp_ports_ok"])
        except Exception:
            ok_val = 0

        if ok_val == 1:
            # Read Inport/Outport counts and names
            try:
                in_ct = int(float(get_engine().workspace["mcp_Inport"]))
            except Exception:
                in_ct = 0
            try:
                out_ct = int(float(get_engine().workspace["mcp_Outport"]))
            except Exception:
                out_ct = 0

            # Read port names from MATLAB workspace
            in_names: list[str] = []
            try:
                raw_in = get_engine().workspace["mcp_Inport_names"]
                if raw_in and hasattr(raw_in, '__iter__'):
                    in_names = [str(x) for x in list(raw_in)]
            except Exception:
                pass
            out_names: list[str] = []
            try:
                raw_out = get_engine().workspace["mcp_Outport_names"]
                if raw_out and hasattr(raw_out, '__iter__'):
                    out_names = [str(x) for x in list(raw_out)]
            except Exception:
                pass

            if in_ct > 0:
                if in_names:
                    labels = ", ".join(in_names)
                    lines.append(f"  Inports: {in_ct} — {labels}")
                else:
                    lines.append(f"  Inports: {in_ct} port(s)")
            if out_ct > 0:
                if out_names:
                    labels = ", ".join(out_names)
                    lines.append(f"  Outports: {out_ct} — {labels}")
                else:
                    lines.append(f"  Outports: {out_ct} port(s)")

        if ok_val == 1:
            # Resolve port semantics for LConn/RConn label annotations
            semantics: dict[str, list[str]] = {}
            try:
                ref_blk = str(matlab_eval(
                    "get_param('" + bp + "','ReferenceBlock')", nargout=1,
                )[0]).strip()
                if ref_blk and ref_blk.lower() != 'none':
                    # get_port_semantics defined below
                    params: dict[str, str] = {}
                    if "Universal Bridge" in ref_blk:
                        try:
                            cv = str(matlab_eval(
                                "get_param('" + bp + "','converterType')", nargout=1,
                            )[0]).strip()
                            params["converterType"] = cv
                        except Exception:
                            pass
                    elif "Series RLC Branch" in ref_blk:
                        try:
                            bt = str(matlab_eval(
                                "get_param('" + bp + "','BranchType')", nargout=1,
                            )[0]).strip()
                            params["BranchType"] = bt
                        except Exception:
                            pass
                    semantics = get_port_semantics(ref_blk, params)
            except Exception:
                pass

            for label, key in [
                ("Enable", "Enable"),
                ("Trigger", "Trigger"),
                ("LConn (power)", "LConn"),
                ("RConn (power)", "RConn"),
            ]:
                try:
                    count = int(float(get_engine().workspace[f"mcp_{key}"]))
                except Exception:
                    count = 0
                if count > 0:
                    if key in semantics and semantics[key]:
                        labels_str = ", ".join(
                            f"[{s}]" for s in semantics[key]
                        )
                        lines.append(f"  {label}: {labels_str} ({count} ports)")
                    else:
                        lines.append(f"  {label}: {count} port(s)")

        get_engine().eval(
            "clear mcp_ports_ok mcp_ports_err"
            " mcp_In mcp_Out mcp_Inport_vals mcp_Inport mcp_Outport_vals mcp_Outport"
            " mcp_Inport_names mcp_Outport_names"
            " mcp_Enable mcp_Enable_vals mcp_Trigger mcp_Trigger_vals"
            " mcp_LConn mcp_LConn_vals mcp_RConn mcp_RConn_vals;",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )

        return "\n".join(lines) if len(lines) > 1 else f"No ports found for '{block_path}'."

    except Exception as e:
        return f"Error getting block ports: {e}"


@mcp.tool()
def get_block_ports(block_path: str = "", block_paths: str = "") -> str:
    """Return the port layout of a Simulink block.

    Shows input/output/enable/trigger/LConn/RConn port numbers and names
    (when available).  Use this before wiring to avoid "invalid port" errors.

    Args:
        block_path: Full block path (e.g. 'mymodel/Gain1').
        block_paths: JSON array of block paths for batch query, e.g.
            '["mymodel/Gain1", "mymodel/Sum1"]'.
    """
    try:
        if block_paths:
            import json
            paths = json.loads(block_paths)
            results = [_get_single_block_ports(p) for p in paths]
            return "\n\n".join(results)
        elif block_path:
            return _get_single_block_ports(block_path)
        else:
            return "Provide either block_path (single) or block_paths (JSON array for batch)."
    except Exception as e:
        return f"Error getting block ports: {e}"


def _ensure_conn_helpers(eng) -> str:
    """Ensure mcp_trace_lines.m and related helpers are on MATLAB path."""
    import os as _os

    d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_ports_helper_")
    matlab_dir = d.replace("\\", "/")
    eng.eval(
        f"addpath('{matlab_dir}'); rehash;",
        nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
    )
    return matlab_dir



def _run_power_audit(model_name: str, search_depth: int = 5) -> dict:
    """Run mcp_audit_power and return structured data.

    Returns:
        {"ok": bool, "blk_list": [...], "ref_list": [...],
         "status": {name: [lines]}, "nodes": [...]}
    """
    eng = get_engine()
    _ensure_conn_helpers(eng)

    eng.eval(
        f"mcp_audit_power('{escape_matlab(model_name)}', {search_depth});",
        nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
    )

    result: dict = {"ok": False, "blk_list": [], "ref_list": [],
                    "status": {}, "nodes": []}

    try:
        ok_val = int(float(eng.workspace["mcp_audit_ok"]))
    except Exception:
        ok_val = 0

    if ok_val != 1:
        try:
            result["err"] = str(eng.workspace["mcp_audit_err"])
        except Exception:
            result["err"] = ""
        return result

    result["ok"] = True

    try:
        blk_list = [str(b).strip() for b in list(eng.workspace["mcp_audit_blk"])]
    except Exception:
        blk_list = []
    try:
        ref_list = [str(r).strip() for r in list(eng.workspace["mcp_audit_refs"])]
    except Exception:
        ref_list = []
    try:
        status_raw = list(eng.workspace["mcp_audit_status"])
        status = {}
        for i, name in enumerate(blk_list):
            if i < len(status_raw):
                status[name] = [str(s).strip() for s in list(status_raw[i])]
            else:
                status[name] = []
    except Exception:
        status = {name: [] for name in blk_list}
    try:
        nodes = [str(n).strip() for n in list(eng.workspace["mcp_audit_nodes"])]
    except Exception:
        nodes = []

    result["blk_list"] = blk_list
    result["ref_list"] = ref_list
    result["status"] = status
    result["nodes"] = nodes
    return result


def _run_signal_audit(model_name: str, search_depth: int = 5) -> dict:
    """Run mcp_audit_signal and return structured data.

    Returns:
        {"ok": bool, "blk_list": [...], "status": {name: [lines]}}
    """
    eng = get_engine()
    _ensure_conn_helpers(eng)

    eng.eval(
        f"mcp_audit_signal('{escape_matlab(model_name)}', {search_depth});",
        nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
    )

    result: dict = {"ok": False, "blk_list": [], "status": {}}

    try:
        ok_val = int(float(eng.workspace["mcp_sp_ok"]))
    except Exception:
        ok_val = 0

    if ok_val != 1:
        try:
            result["err"] = str(eng.workspace["mcp_sp_err"])
        except Exception:
            result["err"] = ""
        return result

    result["ok"] = True

    try:
        count = int(float(eng.workspace["mcp_sp_count"]))
    except Exception:
        count = 0

    try:
        blk_list = [str(b).strip() for b in list(eng.workspace["mcp_sp_blk"])]
    except Exception:
        blk_list = []
    try:
        status_raw = list(eng.workspace["mcp_sp_status"])
        for i, name in enumerate(blk_list):
            if i < len(status_raw):
                result["status"][name] = [str(s).strip() for s in list(status_raw[i])]
    except Exception:
        for name in blk_list:
            result["status"][name] = []

    result["blk_list"] = blk_list
    return result


@mcp.tool()
def describe_block(library_path: str) -> str:
    """Describe a library block: list all parameter names, types, and default values.

    Use this before adding a complex block (transformer, bridge, etc.) to
    know exactly what JSON to pass to add_block or set_block_params.

    Args:
        library_path: Library block path (e.g. 'powerlib/Elements/Series RLC Branch').
    """
    try:
        eng = get_engine()

        # Ensure the source library is loaded before add_block
        lib_name = library_path.split("/")[0]
        if lib_name:
            try:
                eng.eval(f"load_system('{escape_matlab(lib_name)}');",
                         nargout=0, stdout=io.StringIO(), stderr=io.StringIO())
            except Exception:
                pass

        # Use a temp model name that is pure ASCII to avoid encoding issues
        tmp = "mcp_tmp_inspect"
        # Ensure clean state
        try:
            eng.eval(f"bdclose('{tmp}');", nargout=0,
                     stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            pass

        eng.eval(f"new_system('{tmp}');", nargout=0,
                 stdout=io.StringIO(), stderr=io.StringIO())
        eng.eval(
            f"add_block('{escape_matlab(library_path)}', '{tmp}/__blk');",
            nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
        )

        bp = f"{tmp}/__blk"

        # Dialog parameters
        try:
            dp = eng.get_param(bp, "DialogParameters",
                               nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
            param_names = list(dp.keys()) if hasattr(dp, 'keys') else []
        except Exception:
            param_names = []

        lines = [f"Block: {library_path}"]
        try:
            bt = eng.get_param(bp, "BlockType",
                               nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
            lines.append(f"  BlockType: {bt}")
        except Exception:
            lines.append("  BlockType: ?")
        try:
            mt = str(eng.get_param(bp, "MaskType",
                        nargout=1, stdout=io.StringIO(), stderr=io.StringIO()))
            if mt and mt.lower() != "none":
                lines.append(f"  MaskType: {mt}")
        except Exception:
            pass

        # Enrich with MaskPrompts/Styles for masked blocks
        params_prompt = _read_block_params_dict(bp, include_prompts=True)

        lines.append(f"\n  Parameters ({len(params_prompt) or len(param_names)}):")
        if params_prompt:
            for name, val in params_prompt.items():
                lines.append(f"    {name} = {val}")
        else:
            for name in param_names:
                try:
                    val = eng.get_param(bp, name,
                                        nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
                    lines.append(f"    {name} = {val}")
                except Exception:
                    lines.append(f"    {name} = <read-only>")

        # Clean up
        eng.eval(f"bdclose('{tmp}');", nargout=0,
                 stdout=io.StringIO(), stderr=io.StringIO())
        return "\n".join(lines)

    except Exception as e:
        try:
            eng.eval(f"bdclose('{tmp}');", nargout=0,
                     stdout=io.StringIO(), stderr=io.StringIO())
        except Exception:
            pass
        return f"Error describing block: {e}"


_MODEL_CONFIG_PARAMS = [
    "Solver",
    "SolverType",
    "StartTime",
    "StopTime",
    "MaxStep",
    "MinStep",
    "InitialStep",
    "AbsTol",
    "RelTol",
    "SaveOutput",
    "SaveState",
    "SaveTime",
    "SignalLogging",
    "SignalLoggingName",
    "SimulationMode",
]


@mcp.tool()
def get_model_config(model_name: str) -> str:
    """Get model-level simulation configuration parameters.

    Args:
        model_name: Name of the loaded Simulink model.
    """
    try:
        eng = get_engine()

        lines: list[str] = [f"Simulation configuration for '{model_name}':\n"]

        for param in _MODEL_CONFIG_PARAMS:
            try:
                val = eng.get_param(model_name, param,
                                    nargout=1, stdout=io.StringIO(), stderr=io.StringIO())
                lines.append(f"  {param}: {val}")
            except Exception as ex:
                lines.append(f"  {param}: <error: {ex}>")

        return "\n".join(lines)

    except Exception as e:
        return f"Error getting model config: {e}"


_SF_HELPER_DIR: str | None = None


def _ensure_sf_get_helper(eng) -> None:
    """Ensure mcp_get_mf_code.m is on the MATLAB path."""
    global _SF_HELPER_DIR
    import os as _os

    if _SF_HELPER_DIR is None:
        d = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_sf_helper_")
        _os.makedirs(d, exist_ok=True)
        _SF_HELPER_DIR = d.replace("\\", "/")

        get_code = r"""function code = mcp_get_mf_code(block_path)
    bh = get_param(block_path, 'Handle');
    chartId = sf('Private', 'block2chart', bh);
    if chartId == 0
        error('Chart not found: %s', block_path);
    end
    chartObj = sf('IdToHandle', chartId);
    code = chartObj.Script;
end
"""
        p = _os.path.join(d, "mcp_get_mf_code.m").replace("\\", "/")
        current = ""
        try:
            with open(p, "r", encoding="utf-8") as f:
                current = f.read()
        except Exception:
            pass
        if current != get_code:
            with open(p, "w", encoding="utf-8") as f:
                f.write(get_code)

    eng.eval(
        f"addpath('{_SF_HELPER_DIR}'); clear('mcp_get_mf_code');",
        nargout=0, stdout=io.StringIO(), stderr=io.StringIO(),
    )


@mcp.tool()
def get_mfunction_code(block_path: str) -> str:
    """Get the MATLAB code inside a MATLAB Function block.

    Returns the complete function code including the function signature.

    Args:
        block_path: Full path to the MATLAB Function block
            (e.g. 'model/Subsystem/MATLAB_Function').

    Returns:
        The MATLAB code as a string.
    """
    try:
        eng = get_engine()
        _ensure_sf_get_helper(eng)

        raw = str(eng.eval(
            f"mcp_get_mf_code('{escape_matlab(block_path)}');",
            nargout=1, stdout=io.StringIO(), stderr=io.StringIO(),
        ))
        return raw

    except Exception as e:
        return f"Error getting MATLAB Function code: {e}"
"""Port semantics — derive human-readable labels and polarity/phase info for SPS power ports.

Simulink power ports have no built-in names.  This module maps
(ReferenceBlock, key parameters) → port metadata so that audit
output can show functional meanings and detect wiring errors.
"""

import re


def _norm(path: str) -> str:
    """Normalize a Simulink ReferenceBlock path: strip newlines and collapse whitespace."""
    if not path:
        return ""
    return re.sub(r"\s+", " ", path.replace("\n", " ")).strip()


# ── Structured port metadata ──
# Each port entry is a dict: {"label": str, "polarity": str, "phase": str|None}
#   polarity: "+" | "-" | "N" | "AC"
#   phase: "A" | "B" | "C" (only for AC ports), None otherwise
#
# Compatibility rules (same node):
#   "+" ↔ "+" ✓    "+" ↔ "-" ✗ POLARITY_MISMATCH
#   "AC"/"A" ↔ "AC"/"A" ✓    "AC"/"A" ↔ "AC"/"B" ✗ PHASE_MISMATCH
#   "N" ↔ "N" ✓    "N" ↔ "+"/"-"/"AC" ✗
#   Unknown ("?"): skip check


def _p(label: str, polarity: str, phase: str | None = None) -> dict:
    """Shorthand to create a port entry dict."""
    return {"label": label, "polarity": polarity, "phase": phase}


def get_port_semantics(reference_block: str, params: dict | None = None) -> dict[str, list[dict]]:
    """Return port metadata keyed by port type ('LConn', 'RConn', 'Inport', 'Outport').

    Each value is a list of port-entry dicts in Simulink's port order.
    Returns empty dict for unknown blocks.

    Args:
        reference_block: Block ReferenceBlock string (may contain newlines).
        params: Optional dict of block dialog parameters for context-dependent labels.
    """
    rb = _norm(reference_block)
    if params is None:
        params = {}

    # ── Universal Bridge ──
    if rb == "spsUniversalBridgeLib/Universal Bridge":
        converter = str(params.get("converterType", "Inverter"))
        return {
            "Inport": [_p("PWM", "?")],
            "LConn": [_p("A", "AC", "A"), _p("B", "AC", "B"), _p("C", "AC", "C")],
            "RConn": [_p("DC+", "+"), _p("DC-", "-")],
        }

    # ── DC Voltage Source ──
    # Inside the library block, the "+" label is on the right (RConn side)
    # and the "-" label is on the left (LConn side).
    if rb == "spsDCVoltageSourceLib/DC Voltage Source":
        return {
            "LConn": [_p("-", "-")],
            "RConn": [_p("+", "+")],
        }

    # ── Ground ──
    if rb == "spsGroundLib/Ground":
        return {
            "LConn": [_p("GND", "N")],
        }

    # ── Three-Phase Series RLC Branch ──
    if rb == "spsThreePhaseSeriesRLCBranchLib/Three-Phase Series RLC Branch":
        branch_type = str(params.get("BranchType", "RL"))
        if branch_type in ("C", "RC", "RLC"):
            # Shunt: LConn = line side, RConn = neutral/star point
            return {
                "LConn": [_p("A", "AC", "A"), _p("B", "AC", "B"), _p("C", "AC", "C")],
                "RConn": [_p("N_A", "N"), _p("N_B", "N"), _p("N_C", "N")],
            }
        # Series element
        return {
            "LConn": [_p("A-in", "AC", "A"), _p("B-in", "AC", "B"), _p("C-in", "AC", "C")],
            "RConn": [_p("A-out", "AC", "A"), _p("B-out", "AC", "B"), _p("C-out", "AC", "C")],
        }

    # ── Three-Phase V-I Measurement ──
    if rb == "spsThreePhaseVIMeasurementLib/Three-Phase V-I Measurement":
        return {
            "LConn": [_p("InA", "AC", "A"), _p("InB", "AC", "B"), _p("InC", "AC", "C")],
            "RConn": [_p("OutA", "AC", "A"), _p("OutB", "AC", "B"), _p("OutC", "AC", "C")],
        }

    # ── Three-Phase Transformer (Two Windings) ──
    if rb == "spsThreePhaseTransformerTwoWindingsLib/Three-Phase Transformer (Two Windings)":
        return {
            "LConn": [_p("PriA", "AC", "A"), _p("PriB", "AC", "B"), _p("PriC", "AC", "C")],
            "RConn": [_p("SecA", "AC", "A"), _p("SecB", "AC", "B"), _p("SecC", "AC", "C")],
        }

    # ── Three-Phase Programmable Voltage Source ──
    if rb == "spsThreePhaseProgrammableVoltageSourceLib/Three-Phase Programmable Voltage Source":
        return {
            "LConn": [_p("N", "N")],
            "RConn": [_p("A", "AC", "A"), _p("B", "AC", "B"), _p("C", "AC", "C")],
        }

    # ── Unknown ──
    return {}


def port_label(port_type: str, port_num: int, semantics: dict[str, list]) -> str:
    """Build a single port label string like 'RConn(1)[DC+]'.

    Args:
        port_type: e.g. 'LConn', 'RConn', 'Inport', 'Outport'.
        port_num: 1-indexed port number within that type.
        semantics: dict from get_port_semantics (supports both old list[str] and new list[dict]).
    """
    base = f"{port_type}({port_num})"
    entries = semantics.get(port_type, [])
    if port_num <= len(entries) and entries[port_num - 1]:
        entry = entries[port_num - 1]
        if isinstance(entry, dict):
            lbl = entry.get("label", "")
        else:
            lbl = str(entry)
        if lbl:
            return f"{base}[{lbl}]"
    return base


def get_port_info(semantics: dict[str, list], port_type: str, port_num: int) -> dict | None:
    """Return the structured port entry dict for a single port, or None.

    Args:
        semantics: dict from get_port_semantics.
        port_type: e.g. 'LConn', 'RConn'.
        port_num: 1-indexed port number.
    """
    entries = semantics.get(port_type, [])
    if port_num <= len(entries) and entries[port_num - 1]:
        entry = entries[port_num - 1]
        if isinstance(entry, dict):
            return entry
        # Legacy string entry — no polarity info
        return {"label": str(entry), "polarity": "?", "phase": None}
    return None


def check_node_compatibility(port_infos: list[dict]) -> list[str]:
    """Check all ports sharing an electrical node for polarity mismatches.

    Only checks DC polarity (+/−/N). AC phase checks are skipped because
    PortConnectivity.DstBlock does not distinguish individual phases —
    all three phases of a multi-phase block share the same DstBlock set,
    making phase-level node detection unreliable.

    Args:
        port_infos: list of port-entry dicts for all ports on the same node.

    Returns:
        List of mismatch strings (empty if all compatible).
        "POLARITY_MISMATCH: [DC+](+) ↔ [-](−)"
    """
    mismatches: list[str] = []

    # Only check DC +/− polarity. Skip AC phase ports and N (ground/neutral)
    # ports. N is a reference point compatible with any polarity — grounding
    # DC+ or DC- buses is standard practice, not a wiring error.
    known = [
        (i, p) for i, p in enumerate(port_infos)
        if p.get("polarity", "?") not in ("?", "AC", "N")
    ]

    for a_idx in range(len(known)):
        for b_idx in range(a_idx + 1, len(known)):
            ai, pa = known[a_idx]
            bi, pb = known[b_idx]
            pol_a = pa["polarity"]
            pol_b = pb["polarity"]
            lbl_a = pa.get("label", "?")
            lbl_b = pb.get("label", "?")

            # Same polarity: OK
            if pol_a == pol_b:
                continue

            # Different polarities: mismatched
            mismatches.append(
                f"POLARITY_MISMATCH: [{lbl_a}]({pol_a}) ↔ [{lbl_b}]({pol_b})"
            )

    return mismatches
