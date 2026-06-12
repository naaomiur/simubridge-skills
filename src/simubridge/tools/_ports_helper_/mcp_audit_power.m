function ok = mcp_audit_power(model_name, search_depth)
% mcp_audit_power 鈥?Audit every LConn/RConn power port.
%
% Calls mcp_trace_lines for physical line tracing, then formats results.
%
% Output to base workspace (compatible with inspection.py):
%   mcp_audit_count   number of blocks with power ports
%   mcp_audit_blk     cell array of block names
%   mcp_audit_refs    cell array of ReferenceBlock strings
%   mcp_audit_status  cell array of per-block status lines
%   mcp_audit_nodes   cell array of node strings:
%                     "blk_idx|PortType(num); ..."
%   mcp_audit_ok      1 on success

    if nargin < 2 || isempty(search_depth)
        search_depth = 5;
    end

    ok = 0;
    try
        mcp_trace_lines(model_name, {'LConn', 'RConn'}, search_depth);

        tl_ok_val = evalin('base', 'mcp_tl_ok');
        if tl_ok_val ~= 1
            err = evalin('base', 'mcp_tl_err');
            assignin('base', 'mcp_audit_ok', 0);
            assignin('base', 'mcp_audit_err', err);
            return;
        end

        n_blk = evalin('base', 'mcp_tl_n_blk');
        blk_names = evalin('base', 'mcp_tl_blk');
        blk_refs = evalin('base', 'mcp_tl_blk_ref');
        blk_status = evalin('base', 'mcp_tl_blk_status');
        n_nodes = evalin('base', 'mcp_tl_n_nodes');
        nodes = evalin('base', 'mcp_tl_nodes');

        % 鈹€鈹€ Convert node format: "blkIdx|LConn|pn" 鈫?"blkIdx|LConn(pn)" 鈹€鈹€
        audit_nodes = {};
        for ni = 1:n_nodes
            members = nodes{ni};
            if length(members) < 2
                continue;
            end
            parts = {};
            for mi = 1:length(members)
                raw = members{mi};
                tok = strsplit(raw, '|');
                if length(tok) == 3
                    parts{end+1} = sprintf('%s|%s(%s)', tok{1}, tok{2}, tok{3});
                else
                    parts{end+1} = raw;
                end
            end
            audit_nodes{end+1} = strjoin(parts, '; ');
        end

        assignin('base', 'mcp_audit_ok', 1);
        assignin('base', 'mcp_audit_count', n_blk);
        assignin('base', 'mcp_audit_blk', blk_names);
        assignin('base', 'mcp_audit_refs', blk_refs);
        assignin('base', 'mcp_audit_status', blk_status);
        assignin('base', 'mcp_audit_nodes', audit_nodes);
        ok = 1;

    catch ME
        assignin('base', 'mcp_audit_ok', 0);
        assignin('base', 'mcp_audit_err', ME.message);
    end
end
