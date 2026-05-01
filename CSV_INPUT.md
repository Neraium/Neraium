# CSV Input Guide

## Basic command

```
python tools/run_csv.py --csv examples/sample_cnc.csv
```

## CSV requirements

- One row equals one time step
- Numeric columns are treated as sensor signals
- Non-numeric columns are ignored
- Rows with missing numeric values are dropped
- Column order matters because the engine maps columns to sensor positions internally

## Recommended column naming

Use meaningful machine signal names, for example:

- `spindle_vibration`
- `spindle_motor_current`
- `coolant_flow_rate`
- `axis_servo_load`
- `cutting_zone_temperature`

## Output

The runner prints the first confirmed structural change and includes:

- operator output
- engineer output

### What the operator output means

- **what changed**: the detected pattern and a plain English summary
- **where to look**: top signals and relationship pair driving the change, with subsystem and component context
- **trajectory direction**: whether the structural change is diverging, stabilizing, or flat
- **urgency**: how rapidly the trajectory is moving relative to recent history
- **what happens if ignored**: expected behavior if current trend continues
- **what the system is not claiming**: explicit statement of what has not been asserted

### What the engineer output means

- **structural metrics**: drift score, relational stability, and covariance shift at the time of detection
- **evidence families**: which signal families supported the confirmed change
- **contributors**: ranked signals and relationship pairs with covariance and correlation shift values
- **pattern rule**: the rule that triggered the pattern classification

## What this does not do

- does not predict failure time
- does not estimate remaining useful life
- does not assign failure probability
- does not identify exact failed component without machine context

## Optional flags

`--max-rows N`
Limit processing to the first N rows of the CSV.

`--show-transient`
Print a line for each row where the engine returns a transient result, before a confirmed change is detected.

## Closing

Neraium works best when CSV column names reflect real machine signals.
