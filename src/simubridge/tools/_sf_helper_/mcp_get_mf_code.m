function code = mcp_get_mf_code(block_path)
    bh = get_param(block_path, 'Handle');
    chartId = sf('Private', 'block2chart', bh);
    if chartId == 0
        error('Chart not found: %s', block_path);
    end
    chartObj = sf('IdToHandle', chartId);
    code = chartObj.Script;
end
