---
name: sdwan-overlay-architect
description: Design and review SD-WAN overlays across Cisco Catalyst SD-WAN, Palo Alto Prisma, Fortinet, and Versa. Use when adding a site, changing transport colors, or migrating MPLS to DIA.
argument-hint: "[vendor] [site]"
allowed-tools: Read Grep
license: MIT
---

# SD-WAN overlay architect

Do not use for underlay circuit ordering or LAN switching. Not for SASE identity policy (use sase-zero-trust).

## Procedure

1. Inventory transports (MPLS, Internet, LTE/5G) and assign colors. Dual-transport is the default; single-homed sites get an LTE backup.
2. Map application classes to SLA (voice < 150 ms / 30 ms jitter, SaaS probe to the vendor's published POP).
3. Prefer DIA with local breakout for Office 365 / Google / Salesforce; keep PCI and voice on the private overlay.
4. Control policy: TLOC preference, affinity, and hub-and-spoke vs full mesh. Full mesh only inside a region.
5. Verify: cEdge/vEdge BFD up on every color, app-route counters moving, and a failed-color test.

```text
site 2401
  transport mpls     color mpls      preference 200
  transport internet color biz-inet  preference 100
  transport lte      color lte       preference 10
```

## Anti-patterns

- Never put two circuits of the same ISP in different colors and call it diversity.
- Do not enable cloud-on-ramp without an App-ID / URL allow-list.

## Safety

Overlay policy changes ride netops-change-guard. No direct vManage write from the model.
