---
name: campus-nac-dot1x
description: Design and triage campus 802.1X and MAB with ISE or ClearPass. Use when a port will not authorize, a phone+PC daisy-chain fails, or failed-open policy is being reviewed.
argument-hint: "[switch] [port]"
allowed-tools: Read Grep
license: MIT
---

# Campus NAC / 802.1X

Do not use for VPN or ZTNA. Not for firewall identity.

## Procedure

1. Host mode: multi-auth for phone+PC, single-host for servers. MAB only for known printers, with a static MAC group.
2. Failed-closed on access except for emergency failed-open that is time-bounded and logged.
3. dACL / SGT downloaded per session. Default VLAN is a quarantine, not corp.
4. Triage: `show auth sess`, RADIUS live logs, certificate SAN, clock skew.
5. Verify a known-good laptop, a phone, and a printer before calling the port done.

```text
interface Gi1/0/24
  authentication host-mode multi-auth
  authentication periodic
  mab
  dot1x pae authenticator
```

## Anti-patterns

- Never globally disable 802.1X to "get the auditor in".
- Do not MAB a user's laptop.

## Safety

Failed-open is an incident, not a workaround. Change-guard the template.
