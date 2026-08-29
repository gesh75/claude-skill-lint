---
name: firewall-policy-review
description: Review firewall security policy on PAN-OS, FortiOS, and ASA for shadow rules, any-any, and missing log-end. Use when a rule is changing or a quarterly hygiene pass is due.
argument-hint: "[platform] [vsys]"
allowed-tools: Read Grep
license: MIT
---

# Firewall policy review

Do not use for IPS signature tuning or endpoint EDR. Not for SASE SWG categories.

## Procedure

1. Export the rulebase. Hit-count sort. Unused 90-day rules are candidates, not automatic deletes.
2. Flag any-any, any-app, and service-any above a named rule. Shadow detection before inserts.
3. Require log-end and a named owner tag on every allow.
4. App-ID / application overrides: document the exception and an expiry.
5. Verify with a packet that should hit the new rule and a packet that must still hit the old one.

```text
rule 142  src any  dst any  app any  action allow   SHADOWED by 87
rule 210  src 10.8.0.0/16  dst payments  app ssl  action allow  no-log
```

## Anti-patterns

- Never insert at the top "just to test".
- Do not disable a rule without a hit-count export attached to the ticket.

## Safety

Reviews are read-only. Commits are change-guarded and twin-tested on a lab vsys where possible.
