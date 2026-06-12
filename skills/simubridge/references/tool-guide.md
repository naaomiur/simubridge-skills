# SimuBridge 工具速查 · Tool Reference

> 操作前请先用 `model_audit` 了解模型结构。
> Always start with `model_audit` to understand the model structure.

---

## 模型操作 · Model Ops

| Tool | 功能 |
|------|------|
| `open_model(filename)` | 打开 .slx。若已打开先关再开 / Open .slx, reopen if loaded |
| `create_model(name, model_path?)` | 新建空白模型，默认保存到当前目录 |
| `close_model(model_name, save=False)` | 关闭模型，`save=True` 先保存 |
| `save_model(model_name, file_path?)` | 保存，`file_path` 可选另存为 |

## 模块操作 · Block Ops

| Tool | 功能 |
|------|------|
| `search_library(keyword, libraries?, search_depth?)` | 搜索库模块，全词→短语回退。搜索 20+ 常用库 |
| `add_block(destination, source, params?)` | 添加模块。source 可用 JSON 批量 |
| `delete_block(block_path)` | 删除模块，先断所有连线 |
| `describe_block(library_path)` | 列出库模块的全部参数名和默认值，add_block 前先用 |

## 参数操作 · Parameter Ops

| Tool | 功能 |
|------|------|
| `get_block_params(block_path, param_names?)` | 读取参数。含 Mask 提示文本、可见性/使能状态 |
| `set_block_params(block_path, param_name, param_value)` | 单参数设置。枚举支持模糊匹配 |
| `set_block_params(block_path, params_json=...)` | 批量 JSON 设置 |
| `get_model_config(model_name)` | 读取 Solver/StopTime/MaxStep 等 |
| `set_model_config(model_name, params_json)` | JSON 设置仿真参数，枚举支持模糊匹配 |

## 连线 · Wiring

| Tool | 功能 |
|------|------|
| `connect(model_name, src_block, dst_block, src_port, dst_port)` | 单连接 |
| `connect(model_name, src_block, dst_block, src_ports="1,2", dst_ports="3,4")` | 批量连接，两侧要等长 |
| `connect(model_name, src_block, dst_block, src_port, dst_port, src_port_type="LConn")` | 功率连接 |
| `delete_line(model_name, src_block, src_port, dst_block, dst_port)` | 删除连线 |

## 检查 · Inspection

| Tool | 功能 |
|------|------|
| `model_audit(model_name, depth=2)` | 完整拓扑—块列表+Signal/Goto/Data Store/Power 连线+未连接端口 |
| `get_block_ports(block_path)` | 单块端口布局 |
| `get_block_ports(block_paths='["m/Gain1","m/Sum1"]')` | 批量查询 |

## Stateflow · MATLAB Function

| Tool | 功能 |
|------|------|
| `get_mfunction_code(block_path)` | 读取完整代码含函数签名 |
| `set_mfunction_code(block_path, code)` | 写入。完整 function 直接使用，只传函数体自动保留签名 |

## 仿真 · Simulation

| Tool | 功能 |
|------|------|
| `simulate_and_analyze_waveform(model_name, signal_index=1)` | 仿真+分析第 N 个已记录信号 |
| `simulate_and_analyze_waveform(model_name, signal_index=0)` | 列出所有已记录信号 |
| `simulate_and_analyze_waveform(model_name, stop_time=0.5)` | 覆盖仿真时间 |

## 工作区 · Workspace

| Tool | 功能 |
|------|------|
| `get_workspace_vars(var_names="*")` | 列出全部（最多 50 个） |
| `get_workspace_vars(var_names="a,b,c")` | 读取指定变量 |
| `set_workspace_vars(vars_json='{"Kp":10,"Ki":0.5}')` | JSON 写入，支持数字/字符串/数组 |

## 子系统 · Subsystem

| Tool | 功能 |
|------|------|
| `create_subsystem(model_name, block_names, subsystem_name?)` | 打包多个块，block_names 逗号分隔 |
| `expand_subsystem(subsystem_path)` | 展开到父层级，跨界连线尽量重连 |
| `add_subsystem_port(subsystem_path, port_type, port_number, port_name?)` | 添加 Inport/Outport |
| `remove_subsystem_port(subsystem_path, port_type, port_number)` | 删除 Inport/Outport |

## 万能 · Escape Hatch

| Tool | 功能 |
|------|------|
| `eval_matlab(code)` | 执行任意 MATLAB 代码。多行+`;`抑制输出。异常返回 `"Error: ..."` |

---

## 常用库路径

| 模块 | source |
|------|--------|
| Gain | `simulink/Math Operations/Gain` |
| Sum | `simulink/Math Operations/Sum` |
| Product | `simulink/Math Operations/Product` |
| Constant | `simulink/Sources/Constant` |
| Inport | `simulink/Sources/In1` |
| Outport | `simulink/Sinks/Out1` |
| Terminator | `simulink/Sinks/Terminator` |
| Subsystem | `simulink/Ports & Subsystems/Subsystem` |
| MATLAB Function | `simulink/User-Defined Functions/MATLAB Function` |
| Multiport Switch | `simulink/Signal Routing/Multiport Switch` |
| 1-D Lookup Table | `simulink/Lookup Tables/1-D Lookup Table` |
| Data Type Conversion | `simulink/Signal Attributes/Data Type Conversion` |
| Relational Operator | `simulink/Logic and Bit Operations/Relational Operator` |
