---
name: intent-nornir-napalm
description: Build idempotent network intent with Nornir and NAPALM, inventory from NetBox. Use when replacing a hop-by-hop CLI change with a rendered, diffed, dry-run pipeline.
argument-hint: "[play] [site]"
allowed-tools: Read Grep
license: MIT
---

# Intent with Nornir / NAPALM

Do not use for one-off show commands. Not for Ansible-vs-Nornir debates.

## Procedure

1. Inventory from NetBox (nornir-netbox). Filters are site, role, platform — never a handwritten host list.
2. Render Jinja from intent data. No device-specific if-hacks if a platform plugin exists.
3. NAPALM `get_config` + `compare_config` before commit. Print the diff in the ticket.
4. Idempotence: a second run produces an empty diff.
5. Verify on a canary device, then the rest, with change-guard.

```python
from nornir_napalm.plugins.tasks import napalm_configure
r = nr.filter(site="dc1", role="leaf").run(task=napalm_configure, dry_run=True, filename="evpn.j2")
```

## Anti-patterns

- Never `send_command` a config snippet that cannot be diffed.
- Do not keep a parallel YAML inventory "just in case".

## Safety

dry_run is the default. commit is change-guarded.
