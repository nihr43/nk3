# nk3

Fully declarative bare-metal k3s clusters on NixOS.

## motivation

[NixOS](https://nixos.org/) "is a Linux distribution that uses Nix, a tool for reproducible, declarative and reliable package management and system configuration".

These properties make it an excellent choice for 'clean' long-term management of physical k8s nodes.

`nk3` reads a yaml inventory with limited parameters, generates a configuration.nix for each node, lands the config, reboots, and runs health checks.

`inventory.yaml` may resemble the following:

```
---
cluster:
  join_address: 172.30.190.3
  join_token: 2f909ce8-cae1-439a-86b3-da87b7ee9f55
  default_gateway: 172.30.190.1
  nodes:
    172.30.190.3:
      initiator: true
      interface: enp3s0f0
      boot_device: /dev/nvme0n1
    172.30.190.4:
      initiator: false
      interface: enp3s0f0
      boot_device: /dev/nvme0n1
    172.30.190.5:
      initiator: false
      interface: enp3s0f0
      boot_device: /dev/nvme0n1
```
