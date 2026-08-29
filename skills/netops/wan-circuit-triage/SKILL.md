---
name: wan-circuit-triage
description: Triage WAN circuit faults from optics to BGP. Use when a DIA, MPLS, or P2P circuit is down, errored, or saturating and you need an ISP-ready package.
argument-hint: "[circuit-id]"
allowed-tools: Read Grep
license: MIT
---

# WAN circuit triage

Do not use for SD-WAN policy (use sdwan-overlay-architect). Not for LAN.

## Procedure

1. Identify the circuit ID, A/Z ends, last-mile vendor, and the logical overlay color.
2. Physical: admin-up, protocol-up, Rx light in spec, CRC/FCS trend, not a one-second blip.
3. Logical: IP reachability to the PE, BFD, QoS drops. Capture 30 seconds if the fault is intermittent.
4. Open the ISP ticket with circuit ID, timestamps in UTC, light levels, and a ping plot. Ask for an RFO clock.
5. Verify restore: BFD up, error counters flat, overlay SLA recovered.

```text
ckt: IAH-2401-MPLS-001  Rx -8.2 dBm  (spec -2 to -12)
  CRC 4.1e5 last 15m   BFD down 00:12:44Z
  PE 192.0.2.1 unreachable
```

## Anti-patterns

- Never bounce BGP to "see if it comes back" before the physical check.
- Do not give the ISP a screenshot with no circuit ID.

## Safety

Interface flaps are emergency-only and logged.
