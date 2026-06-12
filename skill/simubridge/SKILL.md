---
name: simubridge
description: SimuBridge MCP — AI 驱动的 MATLAB Simulink 模型操作 / AI-driven Simulink model creation, inspection, modification, and simulation. 20+ tools.
---

以下是 SimuBridge MCP 所有工具的详细说明 / Tool reference. 操作前请先 `model_audit` 了解模型结构。

---

## model_audit — 模型拓扑读取 / Topology Audit

读取模型或子系统的完整块列表与所有连线，涵盖四种类型：Signal（信号线）、Goto/From（隐式标签连接）、Data Store（数据存储连接）、Power（SPS 功率连接）。同时报告未连接端口。

Read full model topology — all blocks + all connections (Signal, Goto/From, Data Store, Power). Reports unconnected/dangling ports.

**参数**
- `model_name`：模型名或子系统路径 / model or subsystem path, e.g. `"mymodel"` or `"mymodel/Sub"`
- `depth`（默认 2）：展开深度 / hierarchy depth

---

## search_library — 搜索库模块 / Library Search

在 Simulink 库中按关键词搜索模块，返回可直接传给 `add_block` 的库路径。两阶段搜索：全词匹配 → 自动拆分短语回退。

Search Simulink libraries by keyword, returns paths ready for `add_block`. Two-stage: exact match → phrase fallback.

**参数**
- `keyword`：搜索词 / case-insensitive keyword, e.g. `"Multiport Switch"`
- `libraries`（可选）：逗号分隔的库名 / comma-separated library names

---

## add_block — 添加模块 / Add Block

从库向模型添加模块，支持单个和批量两种模式。添加前逐层验证目标路径是否存在。

Add blocks from library to model. Single or batch mode. Validates paths before adding.

**参数**
- `destination`：目标路径 / e.g. `"mymodel/Gain1"`
- `source`：库路径 / library path, or JSON array for batch
- `params`（可选）：初始参数 JSON / e.g. `'{"Gain":"2.5"}'`

**批量模式 / Batch**：
```json
[{"name":"Gain1","source":"simulink/Math Operations/Gain","params":{"Gain":"3"}}]
```

**常用库路径 / Common sources**

| 模块 | source |
|------|--------|
| Gain | `simulink/Math Operations/Gain` |
| Sum | `simulink/Math Operations/Sum` |
| Constant | `simulink/Sources/Constant` |
| Inport | `simulink/Sources/In1` |
| Outport | `simulink/Sinks/Out1` |
| Subsystem | `simulink/Ports & Subsystems/Subsystem` |
| MATLAB Function | `simulink/User-Defined Functions/MATLAB Function` |
| Multiport Switch | `simulink/Signal Routing/Multiport Switch` |
| Terminator | `simulink/Sinks/Terminator` |

---

## connect — 连接端口 / Connect Ports

连接两个模块的端口，支持信号线和 SPS 功率连接。自动处理嵌套子系统作用域。支持单连接和批量连接。

Wire two block ports — signal or power (SPS). Handles nested subsystems. Single or batch.

**参数**
- `model_name`：父系统路径 / parent system path
- `src_block` / `dst_block`：模块名 / block names
- `src_port` / `dst_port`：单连接端口号 / single port numbers
- `src_ports` / `dst_ports`：批量，逗号分隔 / batch: `"1,2,3"`

---

## delete_block — 删除模块 / Delete Block

删除指定模块，先断开所有连线再删除。

Delete a block, disconnecting all lines first.

**参数**
- `block_path`：完整路径 / e.g. `"mymodel/Sub/GainOld"`

---

## delete_line — 删除连线 / Delete Line

删除指定连线，保留两端模块。支持 SPS 功率连线。

Remove a connection between two ports. Supports power lines.

---

## set_block_params — 设置参数 / Set Params

设置模块的一个或多个参数。枚举参数支持模糊匹配。

Set block parameters. Enum values support fuzzy match.

**参数**
- `block_path`：完整路径
- `param_name` + `param_value`：单参数
- `params_json`：批量 JSON / e.g. `'{"Gain":"2.5","SampleTime":"1e-5"}'`

---

## get_block_params — 读取参数 / Get Params

读取模块当前参数值。

Read current block parameter values.

---

## get_block_ports — 端口信息 / Port Info

返回模块的端口类型和数量。支持单块和批量。

Return port types and counts. Single or batch.

---

## describe_block — 模块详情 / Describe Block

在临时模型中实例化库模块，返回所有参数名及默认值。`add_block` 前的侦察工具。

Instantiate a library block in temp model to inspect all parameters. Use before `add_block`.

---

## set_mfunction_code / get_mfunction_code — MATLAB Function 读写 / Read/Write

写入或读取 MATLAB Function 块代码。写入时自动保留函数签名。

Write/read MATLAB Function block code. Auto-preserves function signature on write.

---

## get_model_config / set_model_config — 模型配置 / Config

读写仿真参数：Solver、StopTime、MaxStep 等。

Read/write simulation config: solver, stop time, step size, etc.

---

## get_workspace_vars / set_workspace_vars — 工作区变量 / Workspace

读写 MATLAB base workspace 变量。`var_names="*"` 列出全部。

Read/write MATLAB workspace variables.

---

## open_model / close_model / save_model / create_model — 模型操作 / Model Ops

打开/关闭/保存/新建 `.slx` 文件。`close_model` 可选 `save=true`。

Open/close/save/create `.slx` files.

---

## create_subsystem / expand_subsystem — 子系统 / Subsystem

将一组块打包成子系统，或展开子系统到父层级。

Group blocks into subsystem, or flatten subsystem to parent.

---

## add_subsystem_port / remove_subsystem_port — 子系统端口 / Port Mgmt

在子系统内部添加/删除 Inport 或 Outport，外部边界自动同步。

Add/remove Inport or Outport inside a subsystem; external boundary updated automatically.

---

## simulate_and_analyze_waveform — 仿真波形 / Simulate

运行仿真并分析已勾选日志的信号，输出包络数据。

Run simulation and analyze logged signals.

**参数**
- `model_name`
- `signal_index`（默认 1）：**传 0 列出所有已记录信号** / pass 0 to list all logged signals
- `stop_time`（可选）

---

## eval_matlab — 执行 MATLAB 代码 / Eval MATLAB

在 MATLAB 引擎中运行任意代码。多行、`;` 抑制输出。

Execute arbitrary MATLAB code in the persistent session.
