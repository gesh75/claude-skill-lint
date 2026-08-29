---
name: observability-dual-signal
description: Gate network alerts on two agreeing signals from independent collectors. Use when a page is noisy, a new check is being added, or an on-call wants to drop a single-counter alarm.
argument-hint: "[service] [signal-a] [signal-b]"
allowed-tools: Read Grep
license: MIT
---

# Dual-signal observability

Do not use for capacity forecasting or flow forensics. Not for log RCA (use a sanitize-first analyzer).

## Procedure

1. Pick two independent planes: interface discards AND synthetic probe; BGP session AND prefix count; syslog AND streaming telemetry.
2. Page only on AND. Slack on OR. Never page on a single SNMP counter.
3. Dedup window 15 minutes. Flaps inside the window are one incident.
4. Every alert names the next command to run and the rollback if a recent change exists.
5. Verify by injecting a fault in the lab and confirming both signals fire.

```text
alert: site-2401-wan-down
  all_of:
    - bfd.color.mpls == down
    - probe.voice.mos < 3.5
  for: 2m
```

## Anti-patterns

- Never page on CPU 80% alone.
- Do not average away a 5-second microburst that drops voice.

## Safety

Alert rule edits are reviewed. Collectors stay read-only against devices.
