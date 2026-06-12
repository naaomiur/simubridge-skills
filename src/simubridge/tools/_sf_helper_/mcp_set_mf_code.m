function mcp_set_mf_code(block_path, file_path)
    rt = sfroot();
    m = rt.find('-isa','Stateflow.Machine');
    model_name = strtok(block_path, '/');
    target_chart = [];
    for i = 1:length(m)
        if strcmp(m(i).Name, model_name)
            charts = m(i).find('-isa','Stateflow.EMChart');
            for j = 1:length(charts)
                if strcmp(charts(j).Path, block_path)
                    target_chart = charts(j);
                    break;
                end
            end
            break;
        end
    end
    if isempty(target_chart)
        error('Chart not found: %s', block_path);
    end

    new_script = fileread(file_path);

    % If the new code does NOT start with "function", preserve the existing
    % function signature from the chart.  This avoids overwriting a named
    % signature like "function v_ref = fcn(theta_m, theta_g, ...)" with the
    % default "function y = fcn(u)".
    new_trimmed = strtrim(new_script);
    if ~startsWith(new_trimmed, 'function')
        old = target_chart.Script;
        nl = find(old == sprintf('\n'), 1);
        if isempty(nl)
            sig = old;  % one-liner — use as-is
        else
            sig = old(1:nl-1);
        end
        new_script = [sig sprintf('\n') new_script];
    end

    target_chart.Script = new_script;
end
