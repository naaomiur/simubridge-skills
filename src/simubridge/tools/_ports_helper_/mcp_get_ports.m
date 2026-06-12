function mcp_get_ports(block_path)
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
