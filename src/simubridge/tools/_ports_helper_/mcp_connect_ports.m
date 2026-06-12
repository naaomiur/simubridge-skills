function ok = mcp_connect_ports(src_block, sp, dst_block, dp, src_type, dst_type)
% Connect two blocks.  sp/dp are port numbers within their type groups.
% Optional src_type / dst_type (e.g. 'LConn', 'RConn') pin the port type
% so the correct port is selected when a block has both LConn and RConn.
% When omitted, all 7 type combinations are tried (backward compatible).

    ok = 0;
    assignin('base', 'mcp_connect_msg', '');

    try
        ph_src = get_param(src_block, 'PortHandles');
        ph_dst = get_param(dst_block, 'PortHandles');
    catch ME
        assignin('base', 'mcp_connect_msg', ME.message);
        return;
    end

    pairs = {
        'LConn', 'LConn';    % 1  same-type (e.g. shunt / ground)
        'RConn', 'RConn';    % 2  same-type (e.g. parallel outputs)
        'RConn', 'LConn';    % 3  series (default power flow)
        'LConn', 'RConn';    % 4  reverse series
        'Outport', 'Inport'; % 5  pure signal
        'Outport', 'LConn';  % 6  signal -> power
        'RConn', 'Inport';   % 7  power -> signal
    };

    sys = get_param(src_block, 'Parent');

    % --- If port types are pinned, only try the specified pair ---
    if nargin >= 6 && ~isempty(src_type) && ~isempty(dst_type)
        try
            src_handles = ph_src.(src_type);
            dst_handles = ph_dst.(dst_type);
        catch
            assignin('base', 'mcp_connect_msg', ...
                sprintf('Port type %s or %s not found on block', src_type, dst_type));
            return;
        end
        if sp <= length(src_handles) && dp <= length(dst_handles)
            ok = try_connect(sys, src_handles(sp), dst_handles(dp), ...
                             src_type, dst_type);
        end
        if ~ok
            src_name = get_param(src_block, 'Name');
            dst_name = get_param(dst_block, 'Name');
            assignin('base', 'mcp_connect_msg', ...
                sprintf('No pair for %s/%s(%d) -> %s/%s(%d)', ...
                        src_name, src_type, sp, dst_name, dst_type, dp));
        end
        return;
    end

    % --- Build overall port number maps for interpretation (b) ---
    type_order = {'Inport','Outport','Enable','Trigger','State', ...
                  'LConn','RConn','Ifaction','Reset','Event'};
    src_map = build_port_map(ph_src, type_order);
    dst_map = build_port_map(ph_dst, type_order);

    % --- Pass 1: sp/dp as per-type-group indices (current semantics) ---
    for i = 1:size(pairs, 1)
        src_type = pairs{i, 1};
        dst_type = pairs{i, 2};
        try
            src_handles = ph_src.(src_type);
            dst_handles = ph_dst.(dst_type);
        catch
            continue;
        end
        if sp <= length(src_handles) && dp <= length(dst_handles)
            ok = try_connect(sys, src_handles(sp), dst_handles(dp), ...
                             src_type, dst_type);
            if ok; return; end
        end
    end

    % --- Pass 2: sp/dp as overall block port numbers ---
    if sp <= length(src_map) && dp <= length(dst_map)
        src_info = src_map{sp};
        dst_info = dst_map{dp};
        for i = 1:size(pairs, 1)
            src_type = pairs{i, 1};
            dst_type = pairs{i, 2};
            if strcmp(src_info.type, src_type) && strcmp(dst_info.type, dst_type)
                ok = try_connect(sys, src_info.handle, dst_info.handle, ...
                                 src_type, dst_type);
                if ok; return; end
            end
        end
    end

    % --- Failed ---
    src_name = get_param(src_block, 'Name');
    dst_name = get_param(dst_block, 'Name');
    assignin('base', 'mcp_connect_msg', ...
        sprintf('No pair for %s/%d -> %s/%d', src_name, sp, dst_name, dp));
end

function ok = try_connect(sys, src_h, dst_h, src_type, dst_type)
% Only clear existing line for signal ports (single-line-per-port).
% Power ports (LConn/RConn) may already be part of a junction —
% add_line will branch off automatically; deleting would destroy the
% existing electrical node.
    ok = 0;
    is_src_power = strcmp(src_type, 'LConn') || strcmp(src_type, 'RConn');
    is_dst_power = strcmp(dst_type, 'LConn') || strcmp(dst_type, 'RConn');

    % Clear existing connection on the DESTINATION port if it is a signal
    % port (an input can only receive from one source).  We do NOT delete on
    % the source side — signal sources support natural branching via add_line.
    if ~is_dst_power
        dst_line = get_param(dst_h, 'Line');
        if dst_line > 0
            delete_line(dst_line);
        end
    end
    try
        add_line(sys, src_h, dst_h, 'autorouting', 'on');
        ok = 1;
        assignin('base', 'mcp_connect_msg', ...
            sprintf('%s->%s', src_type, dst_type));
    catch
        try
            add_line(sys, src_h, dst_h, 'autorouting', 'off');
            ok = 1;
            assignin('base', 'mcp_connect_msg', ...
                sprintf('%s->%s (no auto)', src_type, dst_type));
        catch
        end
    end
end

function map = build_port_map(ph, type_order)
% map{k} = struct('type', string, 'handle', port_handle)
% for the k-th overall port of the block.
    map = {};
    for i = 1:length(type_order)
        t = type_order{i};
        if isfield(ph, t)
            handles = ph.(t);
            for j = 1:length(handles)
                entry.type = t;
                entry.handle = handles(j);
                map{end+1} = entry;
            end
        end
    end
end
