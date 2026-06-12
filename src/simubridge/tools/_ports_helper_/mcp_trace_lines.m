function ok = mcp_trace_lines(model_name, port_types, search_depth)
    if nargin < 2 || isempty(port_types)
        port_types = {'LConn', 'RConn'};
    end
    if nargin < 3 || isempty(search_depth)
        search_depth = 5;
    end
% mcp_trace_lines — Physical line tracing for SPS power circuits.
%
% Direct wires: same line handle on two ports = directly connected.
% Node detection: DstPort-based adjacency (port handles, NOT block handles).
%   DstPort is finer-grained than DstBlock — it tracks individual port
%   handles, so multi-port blocks on different nodes don't cause false merges.
%
% Output to base workspace:
%   mcp_tl_ok            1 on success
%   mcp_tl_n_direct      number of direct wire pairs
%   mcp_tl_dir_from      cell array: "BlkName|LConn|portNum"
%   mcp_tl_dir_to        cell array: "BlkName|RConn|portNum"
%   mcp_tl_n_nodes       number of electrical nodes
%   mcp_tl_nodes         cell array of cell arrays: "blkIndex|PortType|PortNum"
%   (mcp_tl_node_grounded removed — topology-only audit)
%   mcp_tl_n_blk         number of blocks with power ports
%   mcp_tl_blk           cell array of block names
%   mcp_tl_blk_ref       cell array of ReferenceBlock strings
%   mcp_tl_blk_status    cell array of cell arrays: per-block status lines

    ok = 0;
    try
        % Refresh diagram so handles are valid after block edits
        root = strtok(model_name, '/');
        try; set_param(root, 'SimulationCommand', 'update'); catch; end

        blocks = find_system(model_name, 'SearchDepth', search_depth, 'Type', 'block');
        blocks = setdiff(blocks, model_name);

        % ── Phase 1: scan all blocks, collect power ports ──
        blk_names = {};
        blk_handles_list = {};
        blk_refs = {};
        blk_ports = {};  % {bi} = cell of struct(pt, pn, line_h, ph)
        blk_pc = {};     % {bi} = PortConnectivity struct
        line_map = containers.Map('KeyType', 'double', 'ValueType', 'any');

        for i = 1:length(blocks)
            blk = blocks{i};
            try
                ph = get_param(blk, 'PortHandles');
            catch
                continue;
            end
            try
                pc = get_param(blk, 'PortConnectivity');
            catch
                continue;
            end

            ports_list = {};
            for pt_name = port_types
                pt = pt_name{1};
                if isfield(ph, pt)
                    handles = ph.(pt);
                    for pn = 1:length(handles)
                        port_h = handles(pn);
                        try
                            line_h_val = get_param(port_h, 'Line');
                        catch
                            line_h_val = -1;
                        end
                        if line_h_val < 0
                            line_h_val = -1;
                        end
                        ports_list{end+1} = struct('pt', pt, 'pn', pn, ...
                            'line_h', line_h_val, 'ph', port_h);

                        if line_h_val > 0
                            if line_map.isKey(line_h_val)
                                lst = line_map(line_h_val);
                            else
                                lst = {};
                            end
                            lst{end+1} = struct('bi', 0, 'pt', pt, 'pn', pn);
                            line_map(line_h_val) = lst;
                        end
                    end
                end
            end

            if ~isempty(ports_list)
                blk_names{end+1} = strtrim(get_param(blk, 'Name'));
                blk_handles_list{end+1} = get_param(blk, 'Handle');
                try
                    blk_refs{end+1} = get_param(blk, 'ReferenceBlock');
                catch
                    blk_refs{end+1} = '';
                end
                blk_ports{end+1} = ports_list;
                blk_pc{end+1} = pc;
            end
        end

        n_blk = length(blk_names);
        blk_handles = zeros(1, n_blk);
        for bi = 1:n_blk
            blk_handles(bi) = blk_handles_list{bi};
        end

        % ── Phase 1b: fix up line_map bi fields ──
        for bi = 1:n_blk
            ports_list = blk_ports{bi};
            for pi = 1:length(ports_list)
                p = ports_list{pi};
                if p.line_h > 0
                    if line_map.isKey(p.line_h)
                        lst = line_map(p.line_h);
                        found_it = false;
                        for li = 1:length(lst)
                            entry = lst{li};
                            if entry.bi == 0
                                if strcmp(entry.pt, p.pt)
                                    if entry.pn == p.pn
                                        entry.bi = bi;
                                        lst{li} = entry;
                                        line_map(p.line_h) = lst;
                                        found_it = true;
                                        break;
                                    end
                                end
                            end
                        end
                    end
                end
            end
        end

        % ── Phase 2: direct wire pairs (same line handle = physical wire) ──
        dir_from = {};
        dir_to = {};
        direct_lines = containers.Map('KeyType', 'double', 'ValueType', 'logical');

        lh_keys = line_map.keys();
        for k = 1:length(lh_keys)
            lh = lh_keys{k};
            port_list = line_map(lh);
            np = length(port_list);
            if np == 2
                p1 = port_list{1};
                p2 = port_list{2};
                dir_from{end+1} = sprintf('%s|%s|%d', ...
                    blk_names{p1.bi}, p1.pt, p1.pn);
                dir_to{end+1} = sprintf('%s|%s|%d', ...
                    blk_names{p2.bi}, p2.pt, p2.pn);
                direct_lines(lh) = true;
            elseif np > 2
                for a = 1:np
                    for b = a+1:np
                        p1 = port_list{a};
                        p2 = port_list{b};
                        dir_from{end+1} = sprintf('%s|%s|%d', ...
                            blk_names{p1.bi}, p1.pt, p1.pn);
                        dir_to{end+1} = sprintf('%s|%s|%d', ...
                            blk_names{p2.bi}, p2.pt, p2.pn);
                    end
                end
                direct_lines(lh) = true;
            end
        end

        % ── Phase 2b: LineChildren branch detection ──
        % For signal lines with children (branches), each child line segment
        % may have valid SrcPortHandle AND DstPortHandle (both >=0), causing
        % Phase 3 to skip them. Recursively collect leaf children and pair
        % each leaf destination with the root line's source port.
        pair_set = containers.Map('KeyType', 'char', 'ValueType', 'logical');
        for k = 1:length(lh_keys)
            lh = lh_keys{k};
            try
                lc_data = get_param(lh, 'LineChildren');
            catch
                continue;
            end
            if isempty(lc_data)
                continue;
            end

            % Find source port from the root line
            port_list_root = line_map(lh);
            src_tag = '';
            for pi = 1:length(port_list_root)
                p = port_list_root{pi};
                src_tag = sprintf('%s|%s|%d', blk_names{p.bi}, p.pt, p.pn);
                break;
            end
            if isempty(src_tag)
                continue;
            end

            % Recursively collect leaf lines (no LineChildren of their own)
            leaf_lines = {};
            child_stack = lc_data(:)';
            visited = [];
            while ~isempty(child_stack)
                ch = child_stack(1); child_stack(1) = [];
                if ismember(ch, visited)
                    continue;
                end
                visited(end+1) = ch;
                try
                    gc = get_param(ch, 'LineChildren');
                    if isempty(gc)
                        leaf_lines{end+1} = ch;
                    else
                        child_stack = [gc(:)', child_stack];
                    end
                catch
                    leaf_lines{end+1} = ch;
                end
            end

            for li = 1:length(leaf_lines)
                ch = leaf_lines{li};
                if ~line_map.isKey(ch)
                    continue;
                end
                child_ports = line_map(ch);
                for cpi = 1:length(child_ports)
                    cp = child_ports{cpi};
                    dst_tag = sprintf('%s|%s|%d', blk_names{cp.bi}, cp.pt, cp.pn);
                    pair_key = [src_tag ' -> ' dst_tag];
                    if ~pair_set.isKey(pair_key)
                        pair_set(pair_key) = true;
                        dir_from{end+1} = src_tag;
                        dir_to{end+1} = dst_tag;
                    end
                end
            end
        end

        % ── Phase 2c: Goto/From implicit connections ──
        goto_blocks = find_system(model_name, 'SearchDepth', search_depth, ...
            'BlockType', 'Goto');
        from_blocks = find_system(model_name, 'SearchDepth', search_depth, ...
            'BlockType', 'From');
        goto_map = containers.Map('KeyType', 'char', 'ValueType', 'any');
        for i = 1:length(goto_blocks)
            try
                tag = get_param(goto_blocks{i}, 'GotoTag');
                if ~goto_map.isKey(tag)
                    goto_map(tag) = {};
                end
                lst = goto_map(tag);
                lst{end+1} = strtrim(get_param(goto_blocks{i}, 'Name'));
                goto_map(tag) = lst;
            catch
            end
        end
        for i = 1:length(from_blocks)
            try
                tag = get_param(from_blocks{i}, 'GotoTag');
                if goto_map.isKey(tag)
                    from_name = strtrim(get_param(from_blocks{i}, 'Name'));
                    g_list = goto_map(tag);
                    for j = 1:length(g_list)
                        goto_name = g_list{j};
                        src_str = sprintf('%s|%s|%d', goto_name, 'Inport', 1);
                        dst_str = sprintf('%s|%s|%d', from_name, 'Outport', 1);
                        pair_key = [src_str ' -> ' dst_str];
                        if ~pair_set.isKey(pair_key)
                            pair_set(pair_key) = true;
                            dir_from{end+1} = src_str;
                            dir_to{end+1} = dst_str;
                        end
                    end
                end
            catch
            end
        end

        % ── Phase 2d: Data Store Read/Write implicit connections ──
        dsw_blocks = find_system(model_name, 'SearchDepth', search_depth, ...
            'BlockType', 'DataStoreWrite');
        dsr_blocks = find_system(model_name, 'SearchDepth', search_depth, ...
            'BlockType', 'DataStoreRead');
        dsw_map = containers.Map('KeyType', 'char', 'ValueType', 'any');
        for i = 1:length(dsw_blocks)
            try
                dsname = get_param(dsw_blocks{i}, 'DataStoreName');
                if ~dsw_map.isKey(dsname)
                    dsw_map(dsname) = {};
                end
                lst = dsw_map(dsname);
                lst{end+1} = strtrim(get_param(dsw_blocks{i}, 'Name'));
                dsw_map(dsname) = lst;
            catch
            end
        end
        for i = 1:length(dsr_blocks)
            try
                dsname = get_param(dsr_blocks{i}, 'DataStoreName');
                if dsw_map.isKey(dsname)
                    dsr_name = strtrim(get_param(dsr_blocks{i}, 'Name'));
                    w_list = dsw_map(dsname);
                    for j = 1:length(w_list)
                        w_name = w_list{j};
                        src_str = sprintf('%s|%s|%d', w_name, 'Inport', 1);
                        dst_str = sprintf('%s|%s|%d', dsr_name, 'Outport', 1);
                        pair_key = [src_str ' -> ' dst_str];
                        if ~pair_set.isKey(pair_key)
                            pair_set(pair_key) = true;
                            dir_from{end+1} = src_str;
                            dir_to{end+1} = dst_str;
                        end
                    end
                end
            catch
            end
        end

        % ── Phase 3: LineChildren-based junction detection ──
        %
        % Strategy:
        %   3a. Index LineChildren from ALL lines → child→parent map
        %   3b. Group power-port junction lines by their LineChildren parent
        %   3c. Coordinate-based fallback for orphan junction lines
        %   3d. Bridge lines merge groups.  Ground check per node.

        TOL = 0.5;

        % ── 3a: build child->parent index from ALL lines ──
        all_lines = find_system(model_name, 'SearchDepth', search_depth, 'FindAll', 'on', 'Type', 'line');
        child_to_parent = containers.Map('KeyType', 'double', 'ValueType', 'double');
        parent_to_children = containers.Map('KeyType', 'double', 'ValueType', 'any');

        for li = 1:length(all_lines)
            lh = all_lines(li);
            try
                lc = get_param(lh, 'LineChildren');
            catch
                continue;
            end
            if ~isempty(lc)
                parent_to_children(lh) = lc;
                for ci = 1:length(lc)
                    child_to_parent(lc(ci)) = lh;
                end
            end
        end

        % ── 3b: group power port junction lines by parent ──
        parent_nodes = containers.Map('KeyType', 'double', 'ValueType', 'any');
        covered_lh = containers.Map('KeyType', 'double', 'ValueType', 'logical');
        parent_coords = containers.Map('KeyType', 'double', 'ValueType', 'char');

        for bi = 1:n_blk
            ports_list = blk_ports{bi};
            for pi = 1:length(ports_list)
                p = ports_list{pi};
                if p.line_h <= 0; continue; end
                lh = p.line_h;
                if direct_lines.isKey(lh); continue; end

                try; sp = get_param(lh, 'SrcPortHandle'); catch; sp = -1; end
                try; dp = get_param(lh, 'DstPortHandle'); catch; dp = -1; end
                if any(sp >= 0) && any(dp >= 0); continue; end

                tag = sprintf('%d|%s|%d', bi, p.pt, p.pn);

                parent_lh = -1;
                if child_to_parent.isKey(lh)
                    parent_lh = child_to_parent(lh);
                elseif parent_to_children.isKey(lh)
                    parent_lh = lh;
                end

                if parent_lh > 0
                    if ~parent_nodes.isKey(parent_lh)
                        parent_nodes(parent_lh) = {};
                        try
                            pts = get_param(lh, 'Points');
                            if ~isempty(pts)
                                if any(sp == p.ph); jx = round(pts(end,1)); jy = round(pts(end,2));
                                elseif any(dp == p.ph); jx = round(pts(1,1)); jy = round(pts(1,2));
                                else; jx = round(pts(1,1)); jy = round(pts(1,2));
                                end
                                parent_coords(parent_lh) = sprintf('%d,%d', jx, jy);
                            end
                        catch
                        end
                    end
                    lst = parent_nodes(parent_lh);
                    lst{end+1} = tag;
                    parent_nodes(parent_lh) = lst;
                    covered_lh(lh) = true;
                end
            end
        end

        % ── 3c: coordinate fallback for orphan junction lines ──
        orphan_junc = containers.Map('KeyType', 'char', 'ValueType', 'any');

        for bi = 1:n_blk
            ports_list = blk_ports{bi};
            for pi = 1:length(ports_list)
                p = ports_list{pi};
                if p.line_h <= 0; continue; end
                lh = p.line_h;
                if direct_lines.isKey(lh); continue; end
                if covered_lh.isKey(lh); continue; end

                try; sp = get_param(lh, 'SrcPortHandle'); catch; sp = -1; end
                try; dp = get_param(lh, 'DstPortHandle'); catch; dp = -1; end
                if any(sp >= 0) && any(dp >= 0); continue; end

                try; pts = get_param(lh, 'Points'); catch; continue; end
                if isempty(pts); continue; end

                tag = sprintf('%d|%s|%d', bi, p.pt, p.pn);
                jx = -inf; jy = -inf;

                if any(sp == p.ph) && any(dp < 0)
                    jx = round(pts(end,1)); jy = round(pts(end,2));
                elseif any(dp == p.ph) && any(sp < 0)
                    jx = round(pts(1,1)); jy = round(pts(1,2));
                elseif any(sp < 0)
                    jx = round(pts(1,1)); jy = round(pts(1,2));
                end

                if isinf(jx); continue; end

                key = sprintf('%d,%d', jx, jy);
                if orphan_junc.isKey(key)
                    lst = orphan_junc(key);
                else
                    lst = {};
                end
                lst{end+1} = tag;
                orphan_junc(key) = lst;
            end
        end

        % ── 3d: build unified node list + detect bridge lines ──
        node_keys = {};
        node_members = {};

        parent_keys = parent_nodes.keys();
        for i = 1:length(parent_keys)
            plh = parent_keys{i};
            if parent_coords.isKey(plh)
                k = parent_coords(plh);
            else
                k = sprintf('LC_%d', plh);
            end
            node_keys{end+1} = k;
            node_members{end+1} = parent_nodes(plh);
        end

        orphan_keys = orphan_junc.keys();
        for i = 1:length(orphan_keys)
            k = orphan_keys{i};
            node_keys{end+1} = k;
            node_members{end+1} = orphan_junc(k);
        end

        % Bridge lines: both ends at junctions
        bridge_pairs = {};
        all_junc_keys = containers.Map('KeyType', 'char', 'ValueType', 'logical');
        for i = 1:length(node_keys)
            all_junc_keys(node_keys{i}) = true;
        end

        for li = 1:length(all_lines)
            lh = all_lines(li);
            if line_map.isKey(lh); continue; end
            try; sp = get_param(lh, 'SrcPortHandle'); catch; sp = -1; end
            try; dp = get_param(lh, 'DstPortHandle'); catch; dp = -1; end
            if ~(any(sp < 0) && any(dp < 0)); continue; end

            try; pts = get_param(lh, 'Points'); catch; continue; end
            if isempty(pts); continue; end

            jx1 = round(pts(1,1)); jy1 = round(pts(1,2));
            jx2 = round(pts(end,1)); jy2 = round(pts(end,2));
            key1 = sprintf('%d,%d', jx1, jy1);
            key2 = sprintf('%d,%d', jx2, jy2);
            if ~strcmp(key1, key2)
                bridge_pairs{end+1} = {key1, key2};
                all_junc_keys(key1) = true;
                all_junc_keys(key2) = true;
            end
        end

        % BFS adjacency among junction keys
        all_keys = all_junc_keys.keys();
        junc_adj = containers.Map('KeyType', 'char', 'ValueType', 'any');
        for i = 1:length(all_keys)
            junc_adj(all_keys{i}) = {};
        end
        for i = 1:length(bridge_pairs)
            k1 = bridge_pairs{i}{1}; k2 = bridge_pairs{i}{2};
            if junc_adj.isKey(k1); nbrs = junc_adj(k1); nbrs{end+1} = k2; junc_adj(k1) = nbrs; end
            if junc_adj.isKey(k2); nbrs = junc_adj(k2); nbrs{end+1} = k1; junc_adj(k2) = nbrs; end
        end

        junc_visited = containers.Map('KeyType', 'char', 'ValueType', 'logical');
        for i = 1:length(all_keys); junc_visited(all_keys{i}) = false; end

        % Map key → node member indices
        coord_to_idx = containers.Map('KeyType', 'char', 'ValueType', 'any');
        for i = 1:length(node_keys)
            k = node_keys{i};
            if coord_to_idx.isKey(k)
                idxs = coord_to_idx(k);
            else
                idxs = [];
            end
            idxs(end+1) = i;
            coord_to_idx(k) = idxs;
        end

        final_members = {};
        for i = 1:length(all_keys)
            start_key = all_keys{i};
            if junc_visited(start_key); continue; end

            queue = {start_key};
            junc_visited(start_key) = true;
            qptr = 1;
            while qptr <= length(queue)
                key = queue{qptr};
                if junc_adj.isKey(key)
                    nbrs = junc_adj(key);
                    for nj = 1:length(nbrs)
                        nb = nbrs{nj};
                        if junc_visited.isKey(nb) && ~junc_visited(nb)
                            junc_visited(nb) = true;
                            queue{end+1} = nb;
                        end
                    end
                end
                qptr = qptr + 1;
            end

            member_strs = {};
            for qi = 1:length(queue)
                key = queue{qi};
                if coord_to_idx.isKey(key)
                    idxs = coord_to_idx(key);
                    for ii = 1:length(idxs)
                        ni = idxs(ii);
                        if ni <= length(node_members)
                            ms = node_members{ni};
                            for mi = 1:length(ms)
                                member_strs{end+1} = ms{mi};
                            end
                        end
                    end
                end
            end

            if isempty(member_strs); continue; end

            final_members{end+1} = member_strs;
        end

        node_members = final_members;

        % ── Phase 5: per-block status strings ──
        blk_status = cell(1, n_blk);
        for bi = 1:n_blk
            ports_list = blk_ports{bi};
            n_pts = length(ports_list);
            status = cell(1, n_pts);
            for pi = 1:n_pts
                p = ports_list{pi};

                if p.line_h <= 0
                    status{pi} = sprintf('%s(%d): UNCONNECTED', p.pt, p.pn);
                    continue;
                end

                if direct_lines.isKey(p.line_h)
                    % Direct wire — find the other end
                    lst = line_map(p.line_h);
                    others = {};
                    for li = 1:length(lst)
                        pe = lst{li};
                        is_same = 0;
                        if pe.bi == bi
                            if strcmp(pe.pt, p.pt)
                                if pe.pn == p.pn
                                    is_same = 1;
                                end
                            end
                        end
                        if is_same
                            % skip self
                        else
                            others{end+1} = sprintf('%s(%s:%d)', ...
                                blk_names{pe.bi}, pe.pt, pe.pn);
                        end
                    end
                    if isempty(others)
                        others_str = '<self>';
                    else
                        others_str = strjoin(others, ', ');
                    end
                    status{pi} = sprintf('%s(%d): direct -> %s', ...
                        p.pt, p.pn, others_str);
                else
                    % Junction connection — find node
                    my_tag = sprintf('%d|%s|%d', bi, p.pt, p.pn);
                    ni_found = 0;
                    target_str = '';
                    for ni = 1:length(node_members)
                        members = node_members{ni};
                        found = false;
                        for mi = 1:length(members)
                            if strcmp(members{mi}, my_tag)
                                found = true;
                                break;
                            end
                        end
                        if found
                            ni_found = ni;
                            other_parts = {};
                            for mi = 1:length(members)
                                m = members{mi};
                                if strcmp(m, my_tag)
                                    % skip
                                else
                                    other_parts{end+1} = m;
                                end
                            end
                            target_str = sprintf('node %d: %s', ...
                                ni, strjoin(other_parts, ', '));
                            break;
                        end
                    end
                    if ni_found > 0
                        status{pi} = sprintf('%s(%d): — %s', ...
                            p.pt, p.pn, target_str);
                    end
                end
            end
            blk_status{bi} = status;
        end

        % ── Output to workspace ──
        assignin('base', 'mcp_tl_ok', 1);
        assignin('base', 'mcp_tl_n_direct', length(dir_from));
        assignin('base', 'mcp_tl_dir_from', dir_from);
        assignin('base', 'mcp_tl_dir_to', dir_to);
        assignin('base', 'mcp_tl_n_nodes', length(node_members));
        assignin('base', 'mcp_tl_nodes', node_members);
        assignin('base', 'mcp_tl_n_blk', n_blk);
        assignin('base', 'mcp_tl_blk', blk_names);
        assignin('base', 'mcp_tl_blk_ref', blk_refs);
        assignin('base', 'mcp_tl_blk_status', blk_status);
        ok = 1;

    catch ME
        assignin('base', 'mcp_tl_ok', 0);
        assignin('base', 'mcp_tl_err', ME.message);
        assignin('base', 'mcp_tl_err_stack', ME.stack(1).line);
    end
end
