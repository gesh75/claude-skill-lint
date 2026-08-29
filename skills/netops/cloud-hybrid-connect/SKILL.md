---
name: cloud-hybrid-connect
description: Design hybrid cloud interconnects (AWS Direct Connect, Azure ExpressRoute, Google Interconnect) with TGW/VPN backup. Use when attaching a new VPC/VNet or reviewing BGP to a cloud on-ramp.
argument-hint: "[cloud] [region]"
allowed-tools: Read Grep
license: MIT
---

# Cloud hybrid connect

Do not use for IAM or storage design. Not for SD-WAN DIA to SaaS.

## Procedure

1. Two diverse interconnects in two colos. VPN overlay is backup, not the primary data path.
2. BGP: private ASN, MD5 or GTSM, prefix-filters in both directions. Cloud must not default-route you unless intended.
3. Segmentation: prod/nonprod/shared in separate VRFs or TGW route tables. No 0.0.0.0/0 from a VPC into the campus.
4. MACsec on DX/ER where the provider supports it. MTU 8500 if the fabric allows.
5. Verify: failover the primary, confirm RTO, and that the prefix-filter still holds.

```text
DX dx-iad-1  vlan 101  10.255.1.0/31  asn 64512
  advertise 10.24.0.0/16  2001:db8:24::/48
  accept   10.50.0.0/16  2600:1f18::/32
```

## Anti-patterns

- Never accept the cloud's full table "for now".
- Do not share a DX VLAN across prod and a sandbox.

## Safety

Route-filter changes are change-guarded. A leaked default takes the campus to the cloud.
