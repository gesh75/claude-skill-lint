---
name: bgp-evpn-clos
description: Design and triage Clos fabrics with eBGP underlay and EVPN-VXLAN overlay on Juniper, Arista, Cisco, and Nokia. Use when a VTEP is missing, MAC is silent, or a leaf is joining the fabric.
argument-hint: "[leaf] [vni]"
allowed-tools: Read Grep
license: MIT
---

# BGP EVPN Clos

Do not use for campus L2 or WAN BGP. Not for SD-WAN.

## Procedure

1. Underlay first: every leaf has eBGP to both spines, IPv4/IPv6 loopbacks advertised, MTU 9216, BFD 300/300.
2. Overlay: EVPN AF on the same session or a dedicated one. Route-distinguisher unique per VRF per leaf.
3. Confirm IMET + MAC-IP routes. Silent hosts need ARP/ND suppression and anycast GW.
4. Multihoming uses ESI, not spanning-tree. LACP on the server, up/up on both leaves.
5. Verify: `show bgp evpn route`, VXLAN flood-list, and a VM ping across leaves.

```text
protocol bgp {
  group SPINE { type external; local-as 65001; neighbor 10.0.0.1 { peer-as 65100; } }
  family evpn { signaling; }
}
```

## Anti-patterns

- Never run iBGP with route-reflectors on a two-spine fabric.
- Do not reuse RD/RT across tenants.

## Safety

Fabric joins and RT changes go through netops-change-guard with a twin or staging leaf.
