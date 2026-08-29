---
name: netops-change-guard
description: Guard network writes behind dry-run, RFC 6241 confirmed-commit, and explicit rollback. Use when applying config to Cisco, Juniper, Arista, or Nokia and a human must own the blast radius.
argument-hint: "[device] [change-id]"
allowed-tools: Read Grep
license: MIT
---

# Network change guard

Do not use for read-only show commands or lab toys with no production path. Not for firewall policy design.

## Procedure

1. Capture pre-state (`show run`, `show bgp summary`, interface counters) and store it next to the change ticket.
2. Render the candidate config from intent. Diff against running. Reject secrets, `shutdown` of uplinks, and default-route wipes.
3. Apply with confirmed-commit (NETCONF RFC 6241 or vendor equivalent) and a 5–10 minute confirm window.
4. Verify forwarding: ping, traceroute, BGP Established, EVPN MAC count, or synthetic probe — two agreeing signals.
5. Confirm the commit only after verification. Otherwise let it roll back and page the owner.

```xml
<commit>
  <confirmed/>
  <confirm-timeout>600</confirm-timeout>
</commit>
```

## Anti-patterns

- Never `commit` without a confirm window on a PE, spine, or edge firewall.
- Do not paste running-config with TACACS or SNMP strings into an LLM.

## Safety

Read-only until a named human approves the write. Fail closed if rollback is unavailable.
