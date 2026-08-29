---
name: netbox-source-of-truth
description: Treat NetBox as the source of truth for devices, prefixes, VLANs, and cables. Use when planning IP space, racking a leaf, or reconciling a drift between intent and running-config.
argument-hint: "[site] [object]"
allowed-tools: Read Grep
license: MIT
---

# NetBox source of truth

Do not use as a monitoring tool or a substitute for a NMS. Not for flow records.

## Procedure

1. Nothing is real until it is in NetBox. A live device that is missing is drift, not inventory.
2. Allocate prefixes and IDs in NetBox first, then render config. Never the reverse.
3. Cables and rear/front ports are first-class. A "we'll document it later" patch is an incident waiting.
4. Reconcile weekly: NetBox vs CDP/LLDP vs IPAM utilization.
5. Verify the change ticket links the NetBox object IDs.

```python
prefix = nb.ipam.prefixes.create(prefix="2001:db8:24:1::/64", site="dc1", status="active", role="loopback")
```

## Anti-patterns

- Never hand-edit a loopback on a leaf and "catch up NetBox later".
- Do not store secrets in custom fields.

## Safety

NetBox writes are still reviewed. Device writes go through netops-change-guard.
