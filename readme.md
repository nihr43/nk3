# nk3

Long term fully-declarative management of bare-metal k3s clusters on NixOS.

## rationale

[NixOS](https://nixos.org/) "is a Linux distribution that uses Nix, a tool for reproducible, declarative and reliable package management and system configuration".  These properties make it an excellent choice for 'clean' long-term management of physical kubernetes nodes.

`nk3` is the result of years of hacking together ansible roles and wrappers on various OSs and arriving at the conclusion that a single purpose-built tool is best, and declarative rather than cumulative OS configuration is without a doubt the way of the future.

## usage

`nk3` reads a yaml inventory, generates a configuration.nix for each node, lands the config, nixos-rebuilds the node, reboots, and runs health checks where appropriate.  If the new config contains errors discernible by nix, the original running config will be restored.

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

where 172.30.190.3, ... are ips of fresh NixOS boxes with ssh enabled.  These parameters resemble the potential differences between hardware.  Everything else, including hostnames, is derived and templated.

`just` provides and entrypoint:

```
nk3 > just
black .
All done! ✨ 🍰 ✨
3 files left unchanged.
flake8 . --ignore=E501,W503
nix-shell . --run 'python3 main.py'
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
No action needed on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
No action needed on 538f6fb5-5666-5387-9faf-fdea7aa309f7
No action needed on 933fa9c8-51d7-5477-8163-5890a80109bd
```

No changes have been made here.  If we make a change to the config (this cluster has already been bootstrapped, so we no longer need an initiator):

```
  172.30.190.198:
<       initiator: false
---
  172.30.190.198:
>       initiator: true
```

```
nk3 > just
black .
All done! ✨ 🍰 ✨
3 files left unchanged.
flake8 . --ignore=E501,W503
nix-shell . --run 'python3 main.py'
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 modified:
--- 
+++ 
@@ -39,7 +39,7 @@
     role = "server";
     token = "2f909ce8-cae1-439a-86b3-da87b7ee9f55";
 
-    clusterInit = true;
+    serverAddr = "https://172.30.190.198:6443";
 
   };
Rebuilding NixOS on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Rebooting d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
Waiting for d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 become reachable
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
No action needed on 538f6fb5-5666-5387-9faf-fdea7aa309f7
No action needed on 933fa9c8-51d7-5477-8163-5890a80109bd
```

The changed template is applied to the appropriate node, it is rebuilt, it is rebooted, and health of the cluster is asserted.
