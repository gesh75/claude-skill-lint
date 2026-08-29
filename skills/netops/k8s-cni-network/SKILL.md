---
name: k8s-cni-network
description: Design and triage Kubernetes networking with Cilium or Calico, NetworkPolicy, and egress control. Use when pods cannot reach a service, a NetworkPolicy is too open, or a node drops overlay traffic.
argument-hint: "[cluster] [namespace]"
allowed-tools: Read Grep
license: MIT
---

# Kubernetes CNI network

Do not use for app manifest authoring or Helm values. Not for service-mesh mTLS policy in depth.

## Procedure

1. Identify CNI (Cilium eBPF vs Calico iptables/eBPF). Overlay vs native routing vs BGP to the fabric.
2. Services: ClusterIP inside, LoadBalancer via BGP (MetalLB / Cilium BGP) to the ToR, not a cloud NLB in on-prem.
3. NetworkPolicy default-deny per namespace. Egress to DNS and the allowed CIDR only.
4. Node MTU and kube-proxy-free mode. VXLAN fabric MTU must fit.
5. Verify: a probe pod, `cilium connectivity test` or calico equivalent, and a deny that still denies.

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
spec:
  podSelector: {}
  policyTypes: [Ingress, Egress]
  egress:
    - to: [{namespaceSelector: {matchLabels: {name: kube-system}}}]
      ports: [{port: 53, protocol: UDP}]
```

## Anti-patterns

- Never run the cluster overlay on a fabric already doing VXLAN without MTU math.
- Do not leave egress any.

## Safety

CNI swaps are a maintenance window. Policy edits are reviewed.
