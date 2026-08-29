---
name: sase-zero-trust
description: Design SASE and ZTNA access for private apps, SWG, and CASB. Use when replacing VPN, onboarding a connector, or reviewing Prisma / Zscaler / Netskope policy.
argument-hint: "[app] [idp]"
allowed-tools: Read Grep
license: MIT
---

# SASE / Zero Trust

Do not use for branch SD-WAN underlay or classic remote-access IPsec. Not for NAC/802.1X (use campus-nac-dot1x).

## Procedure

1. Classify the app: public SaaS, private HTTP, or private TCP. Private TCP gets a connector, not a VPN pool.
2. Bind identity (IdP group + device posture) before network. No IP-only allow.
3. SWG: TLS decrypt with exceptions for health-care, banking, and pinned apps. Log to the SIEM.
4. Connector placement: two per site, inside the same security zone as the app, health-checked.
5. Verify with a user who is in-group and a user who is not. Confirm the deny is explicit.

```text
policy: payments-api
  from: group=finance AND posture=compliant
  to: app=payments.int.example
  action: allow
  inspect: tls
```

## Anti-patterns

- Never fall back to "any user on the corporate CIDR".
- Do not decrypt banking or healthcare destinations.

## Safety

Policy review is read-only. Connector install is a change-guarded write.
