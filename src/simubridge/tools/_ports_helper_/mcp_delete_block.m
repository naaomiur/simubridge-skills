function mcp_delete_block(block_path)
    % Delete a block and all its connected lines.  Handles all port types
    % (Inport, Outport, LConn, RConn, Enable, Trigger) inside MATLAB to
    % avoid COM encoding issues with PortHandles structs.
    try
        ph = get_param(block_path, 'PortHandles');
        fields = {'Inport', 'Outport', 'Enable', 'Trigger', 'LConn', 'RConn'};
        for f = 1:length(fields)
            try
                ports = ph.(fields{f});
                for p = 1:length(ports)
                    lh = get_param(ports(p), 'Line');
                    if lh > 0
                        delete_line(lh);
                    end
                end
            catch
            end
        end
    catch
    end
    delete_block(block_path);
end
