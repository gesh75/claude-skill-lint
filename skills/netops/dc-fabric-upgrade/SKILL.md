---
name: dc-fabric-upgrade
description: Plan data-center fabric upgrades (ISSU, SMU, or cold) with traffic shift and abort criteria. Use when a spine, leaf, or border-leaf train is moving and you need a sequenced window.
argument-hint: "[role] [from] [to]"
allowed-tools: Read Grep
license: MIT
---

# DC fabric upgrade

Do not use for campus stack upgrades or firewall HA failover. Not for optics swaps without a train change.

## Procedure

1. Read the release notes for the target train: EVPN, BFD, and VXLAN caveats. Lab the SMU on a spare leaf.
2. Shift: one spine at a time, then border, then a canary leaf pair, then the rest. Never two spines.
3. Abort criteria written before the window: BGP session count, EVPN route count, packet loss > 0.1% for 30s.
4. Optics and FEC stay pinned. Do not "also replace QSFP" in the same window.
5. Verify per device: control-plane, forwarding, then the next device.

```text
window Sat 01:00-05:00
  01:00  drain spine-1  confirm ECMP  N-1
  01:40  ISSU spine-1
  02:10  un-drain  watch 15m
  abort if evpn type-2 delta > 1%
```

## Anti-patterns

- Never upgrade both spines because "ISSU is hitless".
- Do not mix a code upgrade with a cabling change.

## Safety

Abort is a first-class step. A failed canary stops the fleet.
