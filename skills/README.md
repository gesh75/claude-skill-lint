# Skills

## `netops/`

22 Agent Skills a senior network engineer actually fires. Each file:

- lints clean at ERROR/WARN on `claude-skill-lint` 0.5
- has a do-not-use boundary, numbered procedure, and verify loop
- is read-only until a named human owns the write

Copy into `~/.claude/skills/<name>/SKILL.md`, or keep this repo mounted so
Claude Code / Managed Agents discover them.

| Skill | Role | Domain |
|-------|------|--------|
| `netops-change-guard` | Senior NE | Change — confirmed-commit + rollback |
| `sdwan-overlay-architect` | Architect | SD-WAN overlay / DIA |
| `sase-zero-trust` | Architect | SASE / ZTNA |
| `bgp-evpn-clos` | Senior NE | EVPN VXLAN Clos |
| `senior-ne-runbook` | Senior NE | Daily triage |
| `network-manager-cadence` | Manager | CAB / change calendar |
| `netbox-source-of-truth` | Engineer | IPAM / DCIM |
| `multivendor-cli-translate` | Engineer | Vendor CLI translate |
| `firewall-policy-review` | Senior NE | PAN / Forti / ASA |
| `observability-dual-signal` | Architect | Dual-signal alerts |
| `ipv6-dual-stack` | Engineer | IPv6 |
| `dc-fabric-upgrade` | Senior NE | Spine/leaf ISSU |
| `wan-circuit-triage` | Engineer | Circuit / underlay |
| `campus-nac-dot1x` | Engineer | 802.1X NAC |
| `dns-dhcp-ipam` | Engineer | DNS / DHCP |
| `k8s-cni-network` | Engineer | Kubernetes CNI |
| `cloud-hybrid-connect` | Architect | DX / ER / Interconnect |
| `mcp-netops-safety` | Senior NE | MCP tool safety |
| `intent-nornir-napalm` | Engineer | Nornir / NAPALM |
| `wifi7-campus` | Engineer | Wi-Fi 6E/7 |
| `mpls-l3vpn` | Senior NE | PE-CE L3VPN |
| `config-diff-preflight` | Engineer | Candidate-config preflight |

```bash
python3 skill_lint.py skills/netops --quiet --min-score 90
```
