# nk3

Sustainable, declarative, safe management of bare-metal k3s clusters on NixOS.

## rationale

[NixOS](https://nixos.org/) "is a Linux distribution that uses Nix, a tool for reproducible, declarative and reliable package management and system configuration".  These properties make it an excellent choice for clean long-term management of physical kubernetes nodes.

`nk3` is the result of years of hacking together ansible roles and wrappers on various OSs and arriving at the conclusion that a single purpose-built tool is best.  Critically, the declarative nature of NixOS is without a doubt the way of the future - rather than cumulative OS configuration or big-hammer nuke-and-pave reimaging on every change.

What do I mean by 'safe'?  The author believes repeatability and determinism are security `requirements`; undefined global mutable state is the root of all evil.

## usage

`nk3` reads a yaml inventory, generates a configuration.nix for each node, lands the config, nixos-rebuilds the node, drains, reboots, uncordons, and runs health checks where appropriate.  If the new config contains errors discernible by nix, the original running config will be restored.  If a change breaks a node such that kubelet doesn't recover after rebooting, the run is aborted.

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
      boot_device: /dev/nvme0n1
    172.30.190.4:
      initiator: false
      boot_device: /dev/nvme0n1
    172.30.190.5:
      initiator: false
      boot_device: /dev/nvme0n1
```

where 172.30.190.3, ... are ips of fresh NixOS boxes with ssh enabled.  These parameters resemble the potential differences between hardware.  Everything else, including hostnames, is derived and templated.

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

## OS Upgrades

`nk3` now supports OS upgrades via `nixos-rebuild boot --upgrade`.

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

Nothing prevents you from attempting something silly like `nixos-24.05` -> `nixos-13.10`, so don't.  Or do, as if it breaks kubernetes the run will halt after the first node is broken.
