---
name: config-diff-preflight
description: Preflight a candidate network config for secrets, blast radius, and silent defaults. Use when a human or an LLM produced a snippet and it must be reviewed before a dry-run.
argument-hint: "[vendor] [file]"
allowed-tools: Read Grep
license: MIT
---

# Config diff preflight

Do not use as a substitute for a digital twin (AEGIS) on high-risk changes. Not for generating the config itself.

## Procedure

1. Diff against running. Reject if the diff includes `no router bgp`, interface shutdowns on uplinks, or AAA removal.
2. Strip and flag secrets: keys, communities used as passwords, TACACS, SNMP.
3. Blast radius: count of peers, prefixes, and interfaces touched. Over a threshold, require a senior.
4. Silent defaults: MTU, BFD, logging, timestamps. Missing logging is a fail.
5. Verify the ticket has pre-state, diff, verification, and rollback pasted.

```diff
- neighbor 192.0.2.1 shutdown
+ neighbor 192.0.2.1 description PE-A
  # fail: this un-shuts a peer without a change window
```

## Anti-patterns

- Never approve a diff you cannot reverse in one command.
- Do not ignore "no" statements that wipe stanzas.

## Safety

A failed preflight stops the pipeline. No override without a named senior.
