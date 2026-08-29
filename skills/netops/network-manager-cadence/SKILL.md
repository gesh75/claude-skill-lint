---
name: network-manager-cadence
description: Run a network manager's weekly and monthly cadence covering CAB, capacity, vendor risk, and staffing. Use when preparing leadership updates, change calendars, or budget narratives.
argument-hint: "[cadence] [month]"
allowed-tools: Read Grep
license: MIT
---

# Network manager cadence

Do not use for packet-level troubleshooting or CLI. Not for writing device templates.

## Procedure

1. Weekly: SEV recap, open changes, circuit RFO aging past 10 days, on-call load.
2. Monthly: capacity (WAN 70% / fabric 40% / IPAM 80% triggers a project), vendor TAC tickets aging, contract renewals inside 120 days.
3. CAB: only changes with a rollback, a verification step, and a named approver. Emergency CAB is the exception, logged.
4. Risk register: single-homed sites, end-of-support hardware, TACACS blast radius, key-person bus factor.
5. Staffing: each engineer has a primary and a backup domain. No domain with one name.

```text
CAB 2026-09-03
  CHG-1841  leaf-24 EVPN RT split     rollback yes   window Sat 02:00
  CHG-1844  Prisma connector pair     rollback yes   window Sun 06:00
  HOLD      core IOS-XR SMU          missing twin test
```

## Anti-patterns

- Never approve a change whose verification is "we'll know if users call".
- Do not let a vendor QBR replace your own capacity numbers.

## Safety

This skill produces documents, not device writes.
