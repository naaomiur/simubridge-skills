function ok = mcp_delete_dangling_lines(model_name, mode)
% mcp_delete_dangling_lines — Use port-side verification to find/delete
% truly dangling lines, avoiding false positives on SPS junction lines.
%
% mode: 'delete' (default) — delete dangling lines
%       'count'            — only count, don't delete
%
% Results via assignin('base', ...):
%   mcp_dangling_count    number of dangling lines found
%   mcp_dangling_deleted  number deleted (0 in 'count' mode)
%   mcp_dangling_ok       1 on success, 0 on fatal error

    if nargin < 2
        mode = 'delete';
    end

    ok = 0;
    try
        % Step 1 — Collect all line handles referenced by any port
        blocks = find_system(model_name, 'Type', 'block');
        blocks = setdiff(blocks, model_name);

        valid_lines = containers.Map('KeyType', 'double', 'ValueType', 'logical');

        for i = 1:length(blocks)
            try
                ph = get_param(blocks{i}, 'PortHandles');
            catch
                continue;
            end

            port_fields = {'Inport', 'Outport', 'LConn', 'RConn', 'Enable', 'Trigger', 'State', 'Ifaction', 'Reset', 'Event'};
            for f = 1:length(port_fields)
                try
                    ports = ph.(port_fields{f});
                catch
                    continue;
                end
                for p = 1:length(ports)
                    if ports(p) <= 0
                        continue;
                    end
                    try
                        lh = get_param(ports(p), 'Line');
                        if lh > 0
                            valid_lines(lh) = true;
                        end
                    catch
                    end
                end
            end
        end

        % Step 2 — Find all line objects in the model
        all_lines = find_system(model_name, 'FindAll', 'on', 'Type', 'line');
        if isempty(all_lines)
            all_lines = [];
        end

        % Step 3 — Identify dangling lines.
        % A line is NOT dangling if it is referenced by any port (Step 1).
        % Intermediate branch segments (line-to-line) are NOT port-referenced
        % but still valid — they have SrcBlockHandle > 0 and DstBlockHandle > 0.
        dangling = [];
        for i = 1:length(all_lines)
            lh = all_lines(i);
            if ~valid_lines.isKey(lh)
                % Secondary check: does this line connect valid blocks?
                try
                    sb = get_param(lh, 'SrcBlockHandle');
                    db = get_param(lh, 'DstBlockHandle');
                    % For DstBlockHandle, check first element of array
                    if isempty(db), db = -1; end
                    if ~isscalar(db), db = db(1); end
                    if ~(sb > 0 && db > 0)
                        dangling(end+1) = lh;  %#ok<AGROW>
                    end
                catch
                    dangling(end+1) = lh;  %#ok<AGROW>
                end
            end
        end

        count = length(dangling);

        % Step 4 — Delete if in 'delete' mode
        deleted = 0;
        if strcmp(mode, 'delete')
            for i = 1:length(dangling)
                try
                    delete_line(dangling(i));
                    deleted = deleted + 1;
                catch
                    % Skip individual lines that fail — don't abort the batch
                end
            end
        end

        assignin('base', 'mcp_dangling_count', count);
        assignin('base', 'mcp_dangling_deleted', deleted);
        assignin('base', 'mcp_dangling_ok', 1);
        ok = 1;
    catch ME
        assignin('base', 'mcp_dangling_count', count);
        assignin('base', 'mcp_dangling_deleted', deleted);
        assignin('base', 'mcp_dangling_ok', 0);
        assignin('base', 'mcp_dangling_err', ME.message);
    end
end
