function ok = mcp_delete_line(src_block, sp, dst_block, dp, src_type, dst_type)
% mcp_delete_line — Delete a single connection between two blocks.
%
% Tries valid port-type combinations. When src_type and dst_type are both
% non-empty, only the specified pair is tried. Otherwise all 7 valid pairs
% are tried, with same-type pairs (LConn/LConn, RConn/RConn, Outport/Inport)
% checked first.
%
% Returns ok = 1 on success, 0 on failure.  Sets mcp_delete_line_err in the
% base workspace on failure so the Python wrapper can include it in the message.

    ok = 0;
    assignin('base', 'mcp_delete_line_err', '');

    try
        ph_src = get_param(src_block, 'PortHandles');
        ph_dst = get_param(dst_block, 'PortHandles');
        src_bh = get_param(src_block, 'Handle');
        dst_bh = get_param(dst_block, 'Handle');
    catch ME
        assignin('base', 'mcp_delete_line_err', ME.message);
        return;
    end

    % ── Build pair list ──
    if ~isempty(src_type) && ~isempty(dst_type)
        % Both types specified — only try that one pair
        pairs = {src_type, dst_type};
    else
        % Same-type pairs first, then cross-type
        all_pairs = {
            'LConn',   'LConn';    % power shunt / ground
            'RConn',   'RConn';    % power parallel
            'Outport', 'Inport';   % signal → signal
            'RConn',   'LConn';    % power series
            'LConn',   'RConn';    % reverse power
            'Outport', 'LConn';    % signal → power
            'RConn',   'Inport';   % power → signal
        };
        if ~isempty(src_type)
            % Filter to pairs whose source type matches
            pairs = {};
            for i = 1:size(all_pairs, 1)
                if strcmp(all_pairs{i, 1}, src_type)
                    pairs{end+1, 1} = all_pairs{i, 1};
                    pairs{end, 2} = all_pairs{i, 2};
                end
            end
        elseif ~isempty(dst_type)
            % Filter to pairs whose dest type matches
            pairs = {};
            for i = 1:size(all_pairs, 1)
                if strcmp(all_pairs{i, 2}, dst_type)
                    pairs{end+1, 1} = all_pairs{i, 1};
                    pairs{end, 2} = all_pairs{i, 2};
                end
            end
        else
            pairs = all_pairs;
        end
    end

    for i = 1:size(pairs, 1)
        st = pairs{i, 1};
        dt = pairs{i, 2};

        if ~isfield(ph_src, st) || ~isfield(ph_dst, dt)
            continue;
        end
        if length(ph_src.(st)) < sp || length(ph_dst.(dt)) < dp
            continue;
        end

        sh = ph_src.(st)(sp);
        dh = ph_dst.(dt)(dp);
        try; lh_src = get_param(sh, 'Line'); catch; continue; end
        try; lh_dst = get_param(dh, 'Line'); catch; continue; end

        % --- Find a usable line handle ---
        lh = 0;
        if lh_src > 0
            lh = lh_src;
        elseif lh_dst > 0
            lh = lh_dst;
        end
        if lh <= 0
            continue;
        end

        % --- Verify the line connects the two blocks ---
        is_signal = strcmp(st, 'Outport') || strcmp(st, 'Inport');
        if is_signal
            try
                line_src_bh = get_param(lh, 'SrcBlockHandle');
                line_dst_bh = get_param(lh, 'DstBlockHandle');
                if (line_src_bh == src_bh && line_dst_bh == dst_bh) || ...
                   (line_src_bh == dst_bh && line_dst_bh == src_bh)
                    delete_line(lh);
                    ok = 1;
                    return;
                end
            catch
            end
        end

        % Power port or signal verification unavailable — delete directly.
        % When port types were specified, this is exactly the right port.
        % When not specified, same-type pairs are checked first, so the
        % correct pair wins for blocks with multiple port types.
        delete_line(lh);
        ok = 1;
        return;
    end

    assignin('base', 'mcp_delete_line_err', ...
        'No port-type pair with a connected line found for these ports');
end
