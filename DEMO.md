# Neraium CNC Demo

## How to run

```
python tools/demo_diverging.py
```

## What this demo represents

A precision CNC machine where multiple signals are monitored over time. After a stable period, the system begins to change structurally.

## What Neraium detects

- Pattern: RELATIONSHIP_FORMATION
- Direction: diverging
- Urgency: high

This means signals that normally behave independently are starting to move together in a new way.

## Example output interpretation

Spindle Motor Current and Spindle Vibration begin moving together more than normal.

This points to a change in how the spindle system is behaving under load.

## Where to look

- Spindle drive
- Spindle assembly

## Recommended action

Inspect the spindle system starting with motor load behavior and vibration coupling.

## What this does NOT claim

- No exact failed component
- No failure time prediction
- No remaining useful life
- No probabilistic failure estimate

## Why this matters

This identifies structural change before traditional alarms or thresholds would trigger.

The goal is to give operators earlier visibility so they can investigate before conditions worsen.
