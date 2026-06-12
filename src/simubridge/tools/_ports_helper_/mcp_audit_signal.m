function ok = mcp_audit_signal(model_name, search_depth)
% mcp_audit_signal 鈥?Audit every Inport/Outport signal port.
%
% Scans all blocks for Inport and Outport ports and reports connection
% status per port: OK (with what it connects to), UNCONNECTED, or ERROR.
%
% Output to base workspace:
%   mcp_sp_ok            1 on success
%   mcp_sp_count          number of blocks with signal ports
%   mcp_sp_blk            cell array of block names
%   mcp_sp_status         cell array of per-block port status lines
%                         each line: "PortName(N): STATUS 鈥?details"

    if nargin < 2 || isempty(search_depth)
        search_depth = 5;
    end

    ok = 0;
    port_types = {'Inport', 'Outport'};

    try
        % Refresh diagram so handles are valid after block edits.
        % Try update first; if that fails, compile+term as fallback.
        root = strtok(model_name, '/');
        try
            set_param(root, 'SimulationCommand', 'update');
        catch
            try
                set_param(root, 'SimulationCommand', 'start');
                set_param(root, 'SimulationCommand', 'stop');
            catch
            end
        end

        blocks = find_system(model_name, 'SearchDepth', search_depth, 'Type', 'block');
        blocks = setdiff(blocks, model_name);

        blk_names = {};
        blk_status = {};

        for bi = 1:length(blocks)
            blk = blocks{bi};
            try
                ph = get_param(blk, 'PortHandles');
            catch
                continue;
            end

            % Resolve port names from internal Inport/Outport blocks
            port_names = containers.Map('KeyType', 'char', 'ValueType', 'any');
            try
                in_blks = find_system(blk, 'SearchDepth', 1, ...
                                      'LookUnderMasks', 'all', 'FollowLinks', 'on', ...
                                      'BlockType', 'Inport');
                names = {};
                for j = 1:length(in_blks)
                    names{j} = get_param(in_blks{j}, 'Name');
                end
                port_names('Inport') = names;
            catch
                port_names('Inport') = {};
            end
            try
                out_blks = find_system(blk, 'SearchDepth', 1, ...
                                       'LookUnderMasks', 'all', 'FollowLinks', 'on', ...
                                       'BlockType', 'Outport');
                names = {};
                for j = 1:length(out_blks)
                    names{j} = get_param(out_blks{j}, 'Name');
                end
                port_names('Outport') = names;
            catch
                port_names('Outport') = {};
            end

            status_lines = {};
            has_port = false;

            for t = 1:length(port_types)
                pt = port_types{t};
                if ~isfield(ph, pt)
                    continue;
                end
                handles = ph.(pt);
                if isempty(handles)
                    continue;
                end
                try
                    names_arr = port_names(pt);
                catch
                    names_arr = {};
                end
                for pn = 1:length(handles)
                    has_port = true;
                    pn_label = num2str(pn);
                    if pn <= length(names_arr) && ~isempty(names_arr{pn})
                        pn_label = sprintf('%d (%s)', pn, names_arr{pn});
                    end
                    try
                        port_h = handles(pn);
                        try
                            lh = get_param(port_h, 'Line');
                        catch
                            lh = -1;
                        end

                        if lh < 0
                            status_lines{end+1} = sprintf('%s(%s): UNCONNECTED', pt, pn_label);
                            continue;
                        end

                        conn_info = get_connected([], pt, pn, ph);
                        if isempty(conn_info)
                            status_lines{end+1} = sprintf('%s(%s): DANGLING 鈥?line exists but no connected block', pt, pn_label);
                        else
                            status_lines{end+1} = sprintf('%s(%s): OK 鈥?%s', pt, pn_label, conn_info);
                        end
                    catch
                        status_lines{end+1} = sprintf('%s(%s): ERROR 鈥?stale handle or inaccessible', pt, pn_label);
                    end
                end
            end

            if has_port
                blk_names{end+1} = strtrim(get_param(blk, 'Name'));
                blk_status{end+1} = status_lines;
            end
        end

        n_blk = length(blk_names);

        assignin('base', 'mcp_sp_ok', 1);
        assignin('base', 'mcp_sp_count', n_blk);
        assignin('base', 'mcp_sp_blk', blk_names);
        assignin('base', 'mcp_sp_status', blk_status);
        ok = 1;

    catch ME
        assignin('base', 'mcp_sp_ok', 0);
        assignin('base', 'mcp_sp_err', ME.message);
    end
end

function info = get_connected(pc, port_type, port_num, ph)
% Find what block/port connects to this signal port via its line handle.
% Wrapped in try/catch 鈥?stale handles after model edits must not crash the audit.
    info = '';
    try
        if ~isfield(ph, port_type) || length(ph.(port_type)) < port_num
            return;
        end
        port_h = ph.(port_type)(port_num);
        try
            lh = get_param(port_h, 'Line');
        catch
            return;
        end
        if lh <= 0
            return;
        end

        try
            sp = get_param(lh, 'SrcPortHandle');
            dp = get_param(lh, 'DstPortHandle');
        catch
            return;
        end

        if strcmp(port_type, 'Inport')
            if any(sp > 0)
                try
                    src_blk = get_param(get_param(sp(1), 'Parent'), 'Handle');
                    nm = get_param(src_blk, 'Name');
                catch
                    return;
                end
                sp_num = get_param(sp(1), 'PortNumber');
                info = sprintf('%s(Outport:%d)', nm, sp_num);
            end
        else  % Outport
            if any(dp > 0)
                try
                    dst_blk = get_param(get_param(dp(1), 'Parent'), 'Handle');
                    nm = get_param(dst_blk, 'Name');
                catch
                    return;
                end
                dp_num = get_param(dp(1), 'PortNumber');
                info = sprintf('%s(Inport:%d)', nm, dp_num);
            end
        end
    catch
        info = '';
    end
end
