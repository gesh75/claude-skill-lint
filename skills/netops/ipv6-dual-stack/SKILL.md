---
name: ipv6-dual-stack
description: Plan and review IPv6 dual-stack on campus, DC, and WAN. Use when numbering a VRF, enabling RA, or deciding NAT64 versus native.
argument-hint: "[site] [vrf]"
allowed-tools: Read Grep
license: MIT
---

# IPv6 dual-stack

Do not use for IPv4-only RFC1918 cleanup. Not for application socket code.

## Procedure

1. Address plan: /48 per site, /64 per VLAN, GUA from the ISP plus ULA for internal-only. No IPv4-think /127 on p2p unless the platform needs it.
2. RA on access, not on routed p2p. Enable RA guard and DHCP-Guard on campus.
3. Dual-stack BGP with a separate IPv6 AF. Do not carry v6 over v4 6PE unless the core cannot.
4. Prefer native end-to-end. NAT64 only for broken SaaS. Document DNS64.
5. Verify: ping6 to the default GW, traceroute6 off-net, and a v6-only test host.

```text
vlan 24
  ipv6 address 2001:db8:24:24::1/64
  ipv6 nd ra hop-limit 64
  ipv6 nd raguard
```

## Anti-patterns

- Never put GUA on a management VRF that should be ULA-only.
- Do not disable RA to "stop the noise" — fix the flood.

## Safety

RA and prefix changes are change-guarded. A bad RA takes the campus down.
