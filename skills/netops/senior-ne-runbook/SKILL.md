---
name: senior-ne-runbook
description: Run senior-network-engineer incident response from first page to RCA. Use when a SEV-1/2 hits BGP, WAN, DC fabric, or firewall and you need a timed, fail-closed playbook.
argument-hint: "[sev] [symptom]"
allowed-tools: Read Grep
license: MIT
---

# Senior NE runbook

Do not use for project design or CAB paperwork (use network-manager-cadence). Not for app-layer incidents.

## Procedure

1. Clock starts. Declare SEV, name an incident commander, open a war-room channel. No config yet.
2. Dual-signal: telemetry AND a human-reproducible symptom. One signal is not a change.
3. Scope: one site, one VRF, one prefix, or global. If global, page the manager.
4. Mitigate with the smallest reversible action (withdraw a prefix, fail over a color, shut a bad peer).
5. After restore: timeline, root cause, detection gap, and one prevention item. No blame.

```text
T+0   declare SEV-2  WAN site 2401  dual-color down
T+5   confirm BFD down both colors  circuit IDs collected
T+12  LTE backup carrying 40%  voice on-net degraded
T+25  ISP restores MPLS  failback  verify MOS
```

## Anti-patterns

- Never bounce BGP as the first step.
- Do not invite vendors before you have a packet capture or log excerpt.

## Safety

Mitigations are change-guarded unless the commander invokes emergency break-glass, which is logged.
