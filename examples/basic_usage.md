# Usage Examples / 使用示例

---

## Example 1: Build a Simple PID Loop / 搭建 PID 回路

```
用户：新建一个叫"pid_demo"的模型，加 Inport、Outport、Sum、一个增益2.5的Gain，
和一个 Integrator，连成反馈回路。

Claude 会做：
1. create_model("pid_demo")
2. add_block 批量添加 Sum/Gain(K=2.5)/Integrator/Inport/Outport
3. connect 连接信号路径和反馈
4. model_audit 验证拓扑

---

User: Create a new model called "pid_demo", add an Inport, Outport,
Sum block, Gain block set to 2.5, and an Integrator.
Connect them in a feedback loop.

Claude will:
1. create_model("pid_demo")
2. add_block batch with Sum, Gain(K=2.5), Integrator, Inport, Outport
3. connect the signal path and feedback
4. model_audit to verify
```

---

## Example 2: Modify Existing Model Parameters / 修改模型参数

```
用户：把"power_system.slx"里的三相电源电压改成480V，频率改成60Hz。

Claude 会做：
1. model_audit("power_system") 找到对应模块
2. get_block_params("power_system/Three-Phase Source") 看当前值
3. set_block_params 写入新值

---

User: In "power_system.slx", change the Three-Phase Source
voltage to 480V and frequency to 60Hz.

Claude will:
1. model_audit("power_system") to find the block
2. get_block_params("power_system/Three-Phase Source") to see current values
3. set_block_params with the new values
```

---

## Example 3: Run Simulation / 运行仿真

```
用户：对"motor_control.slx"运行0.5秒仿真，帮我看速度和转矩波形。

Claude 会做：
1. model_audit 找到已勾选日志的信号名
2. set_model_config 设 stop_time=0.5（如需要）
3. simulate_and_analyze_waveform 跑仿真+返回波形PNG

---

User: Run a simulation of "motor_control.slx" for 0.5 seconds
and show me the speed and torque waveforms.

Claude will:
1. model_audit to find logged signal names
2. set_model_config if needed (stop_time=0.5)
3. simulate_and_analyze_waveform with speed and torque signal names
4. Show the resulting PNG waveform
```

---

## Example 4: Batch Add Blocks / 批量添加模块

```
用户：在"controller.slx"里加三个 Gain 模块，名字分别叫 Kp/Ki/Kd，增益分别 10/0.5/0.1。

Claude 会做：
1. add_block 批量JSON：
   [
     {"name":"Kp","source":"simulink/Math Operations/Gain","params":{"Gain":"10"}},
     {"name":"Ki","source":"simulink/Math Operations/Gain","params":{"Gain":"0.5"}},
     {"name":"Kd","source":"simulink/Math Operations/Gain","params":{"Gain":"0.1"}}
   ]

---

User: Add 3 Gain blocks named Kp, Ki, Kd with gains 10, 0.5, 0.1
to "controller.slx"

Claude will:
1. add_block with batch JSON:
   [
     {"name":"Kp","source":"simulink/Math Operations/Gain","params":{"Gain":"10"}},
     {"name":"Ki","source":"simulink/Math Operations/Gain","params":{"Gain":"0.5"}},
     {"name":"Kd","source":"simulink/Math Operations/Gain","params":{"Gain":"0.1"}}
   ]
```

---

## Example 5: Subsystems / 打包子系统

```
用户：把"demo.slx"里的 Gain 和 Integrator 打成子系统，叫"Plant Model"。

Claude 会做：
1. create_subsystem("demo", ["Gain","Integrator"], "Plant Model")
2. add_subsystem_port 暴露必要的输入输出端口

---

User: Group the Gain and Integrator blocks in "demo.slx"
into a subsystem called "Plant Model"

Claude will:
1. create_subsystem("demo", ["Gain","Integrator"], "Plant Model")
2. add_subsystem_port to expose needed I/O
```

---

## Example 6: MATLAB Function Code / 写 MATLAB Function

```
用户：在"stateflow_demo.slx/Chart"里把状态转换条件改成温度大于100。

Claude 会做：
1. get_mfunction_code 读取当前代码
2. set_mfunction_code 写入更新后的条件和逻辑

---

User: In "stateflow_demo.slx/Chart", change the state transition
condition to use a temperature threshold of 100

Claude will:
1. get_mfunction_code to see current code
2. set_mfunction_code with the updated condition
```
