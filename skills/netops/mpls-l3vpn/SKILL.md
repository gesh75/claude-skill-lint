---
name: mpls-l3vpn
description: Design and triage MPLS L3VPN on PE-CE edges. Use when adding a VRF, dual-homing a CE, or a prefix is missing in a customer VPN.
argument-hint: "[vrf] [pe]"
allowed-tools: Read Grep
license: MIT
---

# MPLS L3VPN

Do not use for EVPN-VXLAN DC fabrics. Not for SD-WAN overlay.

## Procedure

1. RD unique per PE per VRF. RT import/export match the customer's VPN, not a shared "internet" RT.
2. PE-CE: eBGP with prefix-limit, or static with an object-track. Dual-CE uses MED or local-pref, not as-path prepend as the only lever.
3. QoS: classify on CE, exp-map on PE. Voice EF, not a remark later.
4. Core is label-only. Do not leak inet.0 into a customer VRF.
5. Verify: CE ping, PE `show route table vrf`, traceroute showing labels.

```text
vrf FINANCE
  rd 65000:2401
  import target 65000:100
  export target 65000:100
  prefix-limit 200
```

## Anti-patterns

- Never reuse an RD.
- Do not default-originate into a customer VRF without a written request.

## Safety

RT changes can merge VPNs. Twin or offline RR view first.
