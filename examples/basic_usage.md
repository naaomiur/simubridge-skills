# Usage Examples

## Example 1: Build a Simple PID Loop

```
User: Create a new model called "pid_demo", add an Inport, Outport,
Sum block, Gain block set to 2.5, and an Integrator.
Connect them in a feedback loop.

Claude will:
1. create_model("pid_demo")
2. add_block batch with Sum, Gain(K=2.5), Integrator, Inport, Outport
3. connect the signal path and feedback
4. model_audit to verify
```

## Example 2: Modify Existing Model Parameters

```
User: In "power_system.slx", change the Three-Phase Source
voltage to 480V and frequency to 60Hz.

Claude will:
1. model_audit("power_system") to find the block
2. get_block_params("power_system/Three-Phase Source") to see current values
3. set_block_params with the new values
```

## Example 3: Run Simulation and Analyze Results

```
User: Run a simulation of "motor_control.slx" for 0.5 seconds
and show me the speed and torque waveforms.

Claude will:
1. set_model_config if needed (stop_time=0.5)
2. simulate_and_analyze_waveform with speed and torque signal names
3. Show the resulting PNG waveform
```

## Example 4: Batch Add Components

```
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

## Example 5: Working with Subsystems

```
User: Group the Gain and Integrator blocks in "demo.slx"
into a subsystem called "Plant Model"

Claude will:
1. create_subsystem("demo", ["Gain","Integrator"], "Plant Model")
2. add_subsystem_port to expose needed I/O
```

## Example 6: Stateflow Code

```
User: In "stateflow_demo.slx/Chart", change the state transition
condition to use a temperature threshold of 100

Claude will:
1. get_mfunction_code to see current code
2. set_mfunction_code with the updated condition
```
