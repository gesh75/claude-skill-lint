---
name: mcp-netops-safety
description: Design fail-closed MCP tool access to network devices for Claude Code and other agents. Use when adding a NAPALM/Netmiko tool, reviewing allow-lists, or connecting an LLM to a lab or production fabric.
argument-hint: "[tool] [env]"
allowed-tools: Read Grep
license: MIT
---

# MCP NetOps safety

Do not use for skill authoring style (use this repo's linter). Not for general MCP server scaffolding.

## Procedure

1. Default read-only. Write tools are a separate server with a second allow-list.
2. Every tool names device, command class, and whether it mutates. `show` is not `commit`.
3. Sanitize before the model: strip secrets, TACACS, SNMP, and user PII from command output.
4. Production requires a human approval token. Labs may auto-apply under a risk gate.
5. Verify: a denied write, a sanitized syslog line, and an audit HMAC or equivalent.

```text
tool: napalm_get_facts    mutate: no   env: any
tool: napalm_commit       mutate: yes  env: lab|prod+token
tool: netmiko_send_config mutate: yes  env: lab-only
```

## Anti-patterns

- Never give an agent raw Bash on a jump host that can SSH to production.
- Do not log full command output to a cloud LLM without sanitizing.

## Safety

This skill is itself fail-closed. If the policy is unclear, the tool does not fire.
