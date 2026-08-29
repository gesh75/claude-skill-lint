---
name: dns-dhcp-ipam
description: Operate DNS, DHCP, and IPAM as one system. Use when a scope is exhausted, a resolver is poisoned, or a split-horizon zone is drifting from NetBox.
argument-hint: "[scope-or-zone]"
allowed-tools: Read Grep
license: MIT
---

# DNS DHCP IPAM

Do not use for recursive resolver software internals. Not for public DNS marketing records.

## Procedure

1. NetBox is authoritative for prefixes and names. DHCP scopes are carved from NetBox, not from a spreadsheet.
2. Resolvers anycasted (TCP/UDP 53) behind two sites. Health-check the service, not just the VIP.
3. Split horizon: internal views never leak. External views never contain RFC1918.
4. Exhaustion: 80% lease use is a project, 95% is an incident. Scavenge stale first.
5. Verify: `dig +norecurse` against each NS, a new lease on a test port, PTR matches A.

```text
scope 10.24.12.0/24  leases 231/250  92%
  action: reclaim 14 declined  then expand from netbox prefix
```

## Anti-patterns

- Never add a forwarder to 8.8.8.8 "just for this app".
- Do not hand out public DNS as the only campus resolver.

## Safety

Zone edits are reviewed. DHCP option 43/66 changes can take a building down — twin first.
