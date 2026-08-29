---
name: wifi7-campus
description: Design and triage campus Wi-Fi 6E/7 (MLO, 6 GHz, roaming). Use when an SSID is sticky, a floor has retries, or a controller upgrade is planned.
argument-hint: "[building] [ssid]"
allowed-tools: Read Grep
license: MIT
---

# Campus Wi-Fi 7

Do not use for SD-WAN or wired campus NAC except where 802.1X joins the SSID.

## Procedure

1. Spectrum: 5 GHz for density, 6 GHz for capable clients, 2.4 GHz for IoT only. Power and channel from a survey, not auto-max.
2. MLO is a client capability. Do not require it. Fast transition (11r/k/v) stays on.
3. Roaming: OKC, consistent VLAN, no layer-3 roam across buildings without an anchor.
4. Controller: two nodes, config sync verified, certificates with 60-day alert.
5. Verify: a walk test with retries < 10%, roam < 50 ms for voice SSID.

```text
ssid CORP  wpa3-enterprise  11r enabled  band 5+6
ssid IOT   wpa2-psk        band 2.4     isolated
```

## Anti-patterns

- Never raise 2.4 GHz power to "cover the parking lot".
- Do not mix guest and corp on one VLAN.

## Safety

Controller failovers are a window. RF changes are surveyed first.
