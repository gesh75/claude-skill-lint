---
name: multivendor-cli-translate
description: Translate a network task across Cisco IOS-XE/XR, Junos, Arista EOS, Nokia SR Linux, and PAN-OS. Use when you know the intent and need vendor-correct show or config syntax.
argument-hint: "[intent] [vendors]"
allowed-tools: Read Grep
license: MIT
---

# Multivendor CLI translate

Do not use to invent features a platform does not have. Not for NX-OS vs XR personality debates.

## Procedure

1. State the intent in one sentence (e.g. "show EVPN type-2 for 00:11:22:33:44:55").
2. Emit a table: vendor, mode (op/config), exact command, and the field to read.
3. Prefer operational commands. Config snippets include the prompt context (`configure exclusive`, `configure private`).
4. Call out gotchas (Junos pipe vs IOS include, EOS aliases, SR Linux info vs running).
5. Verify against the platform's current train, not memory from 2018.

```text
intent: BGP neighbor state
  IOS-XR   show bgp neighbor brief
  Junos    show bgp neighbor summary
  EOS      show ip bgp summary
  SRL      show network-instance default protocols bgp neighbor
```

## Anti-patterns

- Never mix config and exec in one block without labels.
- Do not guess a hidden command.

## Safety

Output is reference only. Applying it requires netops-change-guard.
