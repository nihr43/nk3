# nk3

`nk3` is a purpose built configuration management tool for declarative, safe, long term operation of bare-metal kubernetes clusters on NixOS.

## rationale

[NixOS](https://nixos.org/) "is a Linux distribution that uses Nix, a tool for reproducible, declarative and reliable package management and system configuration".  These properties make it an excellent choice for clean long-term management of physical kubernetes nodes.

`nk3` is the result of years of hacking together ansible roles and wrappers on various OSs and arriving at the conclusion that a single purpose-built tool is best.  Critically, the declarative nature of NixOS is without a doubt the way of the future - rather than cumulative OS configuration or big-hammer nuke-and-pave reimaging on every change.

## usage

`nk3` reads a yaml inventory, generates a configuration.nix for each node, lands the config, nixos-rebuilds the node, drains, reboots, uncordons, and runs health checks where appropriate.  If the new config contains errors discernible by nix, the original running config will be restored.  If a change breaks a node such that kubelet doesn't recover after rebooting, the run is aborted.

`inventory.yaml` may resemble the following:

```
---
join_address: 172.30.190.3
join_token: woof
nix_channel: nixos-24.05
nodes:
  172.30.190.3:
    initiator: false
    boot_device: /dev/nvme0n1
  172.30.190.4:
    initiator: false
    boot_device: /dev/nvme0n1
  172.30.190.5:
    initiator: false
    boot_device: /dev/nvme0n1
watch_namespaces:
  - default
  - kube-system
  - rook-ceph
```

where 172.30.190.3, ... are ips of fresh NixOS boxes with ssh enabled.  These parameters resemble the potential differences between hardware.  Everything else, including hostnames, is derived and templated.

`watch_namespaces` is a list of namespaces in which daemonsets and deployments should be kept healthy; as in nk3 waits for all deamonset pods to be running, and for 'minimum replicas' of all deployments to be met.

`just` provides an entrypoint:

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

No changes have been made here.  If we make a change to the config:

```
nk3 > just
black .
All done! ✨ 🍰 ✨
4 files left unchanged.
flake8 . --ignore=E501,W503
nix-shell . --run 'python3 main.py'
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
kubelet is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
kubelet is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
kubelet is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
1 daemonsets healthy in namespace default
4 daemonsets healthy in namespace kube-system
7 deployments healthy in namespace default
3 deployments healthy in namespace kube-system
ceph state is HEALTH_OK
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 modified:
--- 
+++ 
@@ -12,6 +12,7 @@
   boot.loader.grub.devices = ["/dev/nvme0n1"];
   boot.tmp.cleanOnBoot = true;
   boot.kernelModules = [ "rbd" ];
+  hardware.cpu.amd.updateMicrocode = true;
 
   environment.systemPackages = with pkgs; [
     htop
Rebuilding NixOS on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Draining d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Rebooting d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
kubelet is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
kubelet is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
kubelet is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 uncordoned
1 daemonsets recovering in namespace default
1 daemonsets healthy in namespace default
4 daemonsets healthy in namespace kube-system
7 deployments healthy in namespace default
3 deployments healthy in namespace kube-system
ceph state is HEALTH_WARN
ceph state is HEALTH_OK
538f6fb5-5666-5387-9faf-fdea7aa309f7 modified:
--- 
+++ 
@@ -12,6 +12,7 @@
   boot.loader.grub.devices = ["/dev/nvme0n1"];
   boot.tmp.cleanOnBoot = true;
   boot.kernelModules = [ "rbd" ];
+  hardware.cpu.amd.updateMicrocode = true;
 
   environment.systemPackages = with pkgs; [
     htop
Rebuilding NixOS on 538f6fb5-5666-5387-9faf-fdea7aa309f7
Draining 538f6fb5-5666-5387-9faf-fdea7aa309f7
Rebooting 538f6fb5-5666-5387-9faf-fdea7aa309f7
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
kubelet is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
kubelet is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
kubelet is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
538f6fb5-5666-5387-9faf-fdea7aa309f7 uncordoned
1 daemonsets healthy in namespace default
4 daemonsets healthy in namespace kube-system
1 deployments recovering in namespace default
1 deployments recovering in namespace default
7 deployments healthy in namespace default
3 deployments healthy in namespace kube-system
ceph state is HEALTH_OK
933fa9c8-51d7-5477-8163-5890a80109bd modified:
--- 
+++ 
@@ -12,6 +12,7 @@
   boot.loader.grub.devices = ["/dev/nvme0n1"];
   boot.tmp.cleanOnBoot = true;
   boot.kernelModules = [ "rbd" ];
+  hardware.cpu.amd.updateMicrocode = true;
 
   environment.systemPackages = with pkgs; [
     htop
Rebuilding NixOS on 933fa9c8-51d7-5477-8163-5890a80109bd
Draining 933fa9c8-51d7-5477-8163-5890a80109bd
Rebooting 933fa9c8-51d7-5477-8163-5890a80109bd
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
kubelet is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
kubelet is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
kubelet is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
933fa9c8-51d7-5477-8163-5890a80109bd uncordoned
1 daemonsets recovering in namespace default
1 daemonsets healthy in namespace default
4 daemonsets healthy in namespace kube-system
7 deployments healthy in namespace default
3 deployments healthy in namespace kube-system
ceph state is HEALTH_WARN
ceph state is HEALTH_WARN
ceph state is HEALTH_OK
```

The changed template is applied, nodes are rebuilt, rebooted, and health of the cluster is asserted.

## OS Upgrades

`nk3` supports OS upgrades via `nixos-rebuild boot --upgrade`.

```
nk3 > nix-shell . --run 'python3 main.py --upgrade'
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
ceph state is HEALTH_OK
Rebuilding NixOS on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Draining d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Rebooting d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 uncordoned
ceph state is HEALTH_WARN
ceph state is HEALTH_WARN
ceph state is HEALTH_OK
Kernel upgraded from 6.6.45 to 6.6.46 on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
Rebuilding NixOS on 538f6fb5-5666-5387-9faf-fdea7aa309f7
Draining 538f6fb5-5666-5387-9faf-fdea7aa309f7
Rebooting 538f6fb5-5666-5387-9faf-fdea7aa309f7
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
538f6fb5-5666-5387-9faf-fdea7aa309f7 uncordoned
ceph state is HEALTH_WARN
ceph state is HEALTH_WARN
ceph state is HEALTH_OK
Kernel upgraded from 6.6.45 to 6.6.46 on 538f6fb5-5666-5387-9faf-fdea7aa309f7
Rebuilding NixOS on 933fa9c8-51d7-5477-8163-5890a80109bd
Draining 933fa9c8-51d7-5477-8163-5890a80109bd
Rebooting 933fa9c8-51d7-5477-8163-5890a80109bd
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
933fa9c8-51d7-5477-8163-5890a80109bd uncordoned
ceph state is HEALTH_WARN
ceph state is HEALTH_WARN
ceph state is HEALTH_WARN
ceph state is HEALTH_OK
Kernel upgraded from 6.6.45 to 6.6.46 on 933fa9c8-51d7-5477-8163-5890a80109bd
```

`nix-channel` is sourced from the inventory, and enforced on each `--upgrade`:

```
if args.upgrade:
    channel_cmd = f"nix-channel --add https://nixos.org/channels/{cluster.nix_channel} nixos"
```

(--add is idempotent when the same name is given)

Thus, to trigger a full nixos release upgrade, simply increment `nix_channel:` in the inventory.
We do not define `system.stateVersion` in configuration.nix, allowing nixos-rebuild to default to the current channel.  This is fine for the time being, as k3s is unaffected by the parameter (`grep -ir stateVersion nixpkgs/nixos/modules/`).

If a bogus channel is given, the system will abort:

```
nk3 > nix-shell . --run 'python3 main.py -u'
d752cf78-d889-5bd9-8dd4-2bb7eeb898f4 is reachable
538f6fb5-5666-5387-9faf-fdea7aa309f7 is reachable
933fa9c8-51d7-5477-8163-5890a80109bd is reachable
k8s is ready on 538f6fb5-5666-5387-9faf-fdea7aa309f7
k8s is ready on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4
k8s is ready on 933fa9c8-51d7-5477-8163-5890a80109bd
ceph state is HEALTH_OK
Rebuilding NixOS on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4

error: unable to download 'https://nixos.org/channels/woofwoof': HTTP error 404

       response body:

       <html>
       <head><title>404 Not Found</title></head>
       <body>
       <h1>404 Not Found</h1>
       <ul>
       <li>Code: NoSuchKey</li>
       <li>Message: The specified key does not exist.</li>
       <li>Key: woofwoof</li>
       <li>RequestId: WHEKMHS24749WRMB</li>
       <li>HostId: VUgZO7OBuSXfhmEUa+PJQGiuPbzQH8Sl6As737i8fl4qkFFUyqhBdW0cQzIobB4smD928pt5RZs=</li>
       </ul>
       <hr/>
       </body>
       </html>

`nixos-rebuild` failed on d752cf78-d889-5bd9-8dd4-2bb7eeb898f4.  Changes reverted
Traceback (most recent call last):
  File "/home/nhensel/git/nk3/main.py", line 248, in <module>
    sys.exit(main())
             ^^^^^^
  File "/home/nhensel/git/nk3/main.py", line 214, in main
    raise RuntimeError()
RuntimeError
```
