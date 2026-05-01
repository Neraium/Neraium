# Neraium

Neraium detects structural change in complex systems and characterizes how that change is evolving.

## What The System Does

- Detects structural change using multi-signal evidence
- Identifies contributing signals and relationships
- Classifies structural patterns
- Determines trajectory direction
- Provides operator and engineer views

## What The System Does NOT Do

- Does not predict failure time
- Does not estimate remaining useful life
- Does not assign failure probabilities
- Does not infer physical root cause
- Does not require labeled failure data

## Core Outputs

Neraium exposes three output views from the same engine result.

`operator` output is the decision signal. It provides the current status, a concise description of what is happening, where to inspect, trajectory direction, relative urgency, and recommended next step.

`engineer` output is the audit trail. It exposes structural metrics, trajectory metrics, evidence families, contributors, and pattern rule information without adding summaries or interpretation.

`raw_engine` output is the full engine result. It preserves the complete internal output used to build the operator and engineer views.

## Output Philosophy

Neraium does not attempt to predict when a system will fail. It detects when a system is no longer behaving like its learned baseline and characterizes how that change is evolving.

## Interpretation Rules

- `CONFIRMED_CHANGE` requires persistence and multi-family evidence
- Patterns describe structure, not failure modes
- Trajectory describes direction, not outcome
- Urgency is relative, not absolute
- If ignored describes expected behavior, not prediction

## Development Status

- Phase 1: evidence gate complete
- Phase 2: contributors complete
- Phase 3: pattern classification complete
- Phase 4: trajectory complete
- Engine orchestration complete
- Operator output complete
- Engineer output complete
- System output wrapper complete

## Running The System

```bash
python tools/replay_system_output.py
```

Neraium provides structural visibility. It does not replace human judgment.
