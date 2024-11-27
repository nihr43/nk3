import os
import sys
import time
import yaml
import json
import difflib
import uuid
import argparse
import traceback
import logging
import ipaddress
import fabric
from io import StringIO
from invoke.exceptions import UnexpectedExit
from termcolor import colored
from jinja2 import Environment, FileSystemLoader
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.getLogger("paramiko").setLevel(logging.CRITICAL)


class Cluster:
    def __init__(self, join_address, join_token, nodes, nix_channel, namespaces):
        self.join_address = join_address
        self.join_token = join_token
        self.nodes = nodes
        self.nix_channel = nix_channel
        self.namespaces = namespaces

    @classmethod
    def from_yaml(cls, args):
        with open(args.inventory, "r") as file:
            data = yaml.safe_load(file)
            join_address = data["join_address"]
            join_token = data["join_token"]
            nix_channel = data["nix_channel"]
            namespaces = data["watch_namespaces"]
            nodes = []
            for n, d in data["nodes"].items():
                nodes.append(Node(n, d["initiator"], d["boot_device"], args))
            return cls(join_address, join_token, nodes, nix_channel, namespaces)

    def k8s_ready(self):
        for n in self.nodes:
            n.k8s_ready()

    def ceph_ready(self):
        self.nodes[0].ceph_ready()

    def daemonsets_ready(self, namespace: str):
        i = 0
        while i < 600:
            i += 1
            try:
                result = self.nodes[0].ssh.run(
                    f"kubectl get daemonset -o json -n {namespace}"
                )
                js = json.loads(result.stdout)
                desired_healthy = len(js["items"])
                healthy = 0
                for ds in js["items"]:
                    if (
                        ds["status"]["numberAvailable"]
                        == ds["status"]["desiredNumberScheduled"]
                    ):
                        healthy += 1
                if healthy == desired_healthy:
                    print(
                        colored(
                            f"{healthy} daemonsets healthy in namespace {namespace}",
                            "green",
                        )
                    )
                    return
                else:
                    if i % 10 == 0:
                        unhealthy = desired_healthy - healthy
                        print(
                            f"{unhealthy} daemonsets recovering in namespace {namespace}"
                        )
                    time.sleep(1)
                    continue
            except json.decoder.JSONDecodeError:
                time.sleep(1)
                continue

        raise TimeoutError

    def deployments_ready(self, namespace):
        i = 0
        while i < 600:
            i += 1
            try:
                result = self.nodes[0].ssh.run(
                    f"kubectl get deployment -o json -n {namespace}"
                )
                js = json.loads(result.stdout)
                desired_healthy = len(js["items"])
                healthy = 0
                for d in js["items"]:
                    for condition in d["status"]["conditions"]:
                        if (
                            condition["reason"] == "MinimumReplicasAvailable"
                            and condition["status"] == "True"
                        ):
                            healthy += 1
                            break
                if healthy == desired_healthy:
                    print(
                        colored(
                            f"{healthy} deployments healthy in namespace {namespace}",
                            "green",
                        )
                    )
                    return
                else:
                    if i % 10 == 0:
                        unhealthy = desired_healthy - healthy
                        print(
                            f"{unhealthy} deployments recovering in namespace {namespace}"
                        )
                    time.sleep(1)
                    continue
            except json.decoder.JSONDecodeError:
                time.sleep(1)
                continue

        raise TimeoutError


class Node:
    def __init__(self, ip, initiator, boot_device, args):
        self.ip = ip
        self.boot_device = boot_device
        self.initiator = initiator
        self.name = uuid.uuid5(uuid.NAMESPACE_OID, self.ip)
        self.args = args
        self.ssh_ready()
        self.interface = self.get_interface()
        self.gateway = self.get_gateway()

    def get_interface(self):
        result = self.ssh.run("ip r get 1.1.1.1 | awk '/via/{print $5}'")
        interface = result.stdout.strip()
        if interface.startswith(("eth", "eno", "enp")):
            return interface
        else:
            raise NotImplementedError(interface)

    def get_gateway(self):
        result = self.ssh.run("ip r get 1.1.1.1 | awk '/via/{print $3}'")
        gw = result.stdout.strip()
        try:
            ipaddress.IPv4Address(gw)
            return gw
        except ipaddress.AddressValueError as e:
            raise e

    def ssh_ready(self):
        i = 0
        while i < 300:
            i += 1
            if i % 10 == 0:
                print("Waiting for {} to become reachable".format(self.name))
            try:
                if self.args.private_key:
                    print(f"using {self.args.private_key}")
                    self.ssh = fabric.Connection(
                        host=self.ip,
                        user="root",
                        connect_kwargs={"key_filename": self.args.private_key},
                        config=fabric.config.Config(overrides={"run": {"hide": True}}),
                    )
                else:
                    self.ssh = fabric.Connection(
                        host=self.ip,
                        user="root",
                        config=fabric.config.Config(overrides={"run": {"hide": True}}),
                    )
                self.ssh.run("hostname")
                print("{} is reachable".format(self.name))
                return
            except (TimeoutError, EOFError, NoValidConnectionsError):
                time.sleep(1)
                continue

        raise TimeoutError

    def k8s_ready(self):
        i = 0
        while i < 600:
            i += 1
            try:
                result = self.ssh.run("kubectl get node {} -o json".format(self.name))
                node_json = json.loads(result.stdout)
                for condition in node_json["status"]["conditions"]:
                    if (
                        condition["reason"] == "KubeletReady"
                        and condition["status"] == "True"
                    ):
                        print(
                            colored("kubelet is ready on {}".format(self.name), "green")
                        )
                        return
                    elif (
                        condition["reason"] == "KubeletReady"
                        and condition["status"] == "False"
                    ):
                        print("kubelet is not ready on {}".format(self.name))
                        time.sleep(1)
                        continue
            except (json.decoder.JSONDecodeError, ConnectionResetError, UnexpectedExit):
                time.sleep(1)
                continue

        raise TimeoutError

    def ceph_ready(self):
        i = 0
        while i < 600:
            i += 1
            result = self.ssh.run(
                "kubectl -n rook-ceph exec deployment/rook-ceph-tools --pod-running-timeout=5m -- ceph status -f json"
            )
            try:
                js = json.loads(result.stdout)
            except json.decoder.JSONDecodeError:
                time.sleep(1)
                continue
            health = js["health"]["status"]
            if i % 10 == 0 and health != "HEALTH_OK":
                print(f"ceph state is {health}")
            if health == "HEALTH_OK":
                print(colored(f"ceph state is {health}", "green"))
                return
            else:
                time.sleep(1)

        raise TimeoutError


def reconcile(node, cluster, args):
    file_loader = FileSystemLoader("templates/")
    env = Environment(loader=file_loader)
    template = env.get_template("configuration.nix")
    output = template.render(node=node, cluster=cluster)

    output_file_path = "artifacts/{}".format(node.name)
    with open(output_file_path, "w") as f:
        f.write(output)

    with open(output_file_path, "r") as local_file:
        local_config = local_file.read()

    remote_config = node.ssh.run("cat /etc/nixos/configuration.nix").stdout

    diff = list(
        difflib.unified_diff(remote_config.splitlines(), local_config.splitlines())
    )

    if diff:
        print("{} modified:".format(node.name))
        diff_formatted = colored("\n".join(diff), "yellow")
        print(diff_formatted)
        node.ssh.put(local=output_file_path, remote="/etc/nixos/configuration.nix")

    if diff or args.upgrade:
        print(f"Rebuilding NixOS on {node.name}")
        if args.upgrade:
            result = node.ssh.run("uname -r")
            initial_kernel = result.stdout.strip()
            channel_cmd = f"nix-channel --add https://nixos.org/channels/{cluster.nix_channel} nixos"
            try:
                node.ssh.run(channel_cmd)
            except UnexpectedExit as e:
                print(e)
                sys.exit(1)
            nixos_cmd = f"nixos-rebuild {args.nixos_action} --upgrade"
        else:
            nixos_cmd = f"nixos-rebuild {args.nixos_action}"

        try:
            result = node.ssh.run(nixos_cmd)
        except UnexpectedExit as e:
            # if rebuild faild, write the original back
            membuf = StringIO(remote_config)
            node.ssh.put(membuf, remote="/etc/nixos/configuration.nix")
            print(e)
            print(f"`nixos-rebuild` failed on {node.name}.  Changes reverted.")
            os._exit(1)
        else:
            if args.verbose:
                print(result.stdout)
                print(result.stderr)

            no_action = """unpacking channels...
building Nix...
building the system configuration...
updating GRUB 2 menu...
"""

            if args.upgrade and result.stderr == no_action:
                print(colored(f"No upgrade needed on {node.name}", "yellow"))
                return
            if args.nixos_action == "boot":
                print(f"Draining {node.name}")
                try:
                    result = node.ssh.run(
                        f"kubectl drain {node.name} --ignore-daemonsets --delete-emptydir-data"
                    )
                except UnexpectedExit as e:
                    print(e)
                    sys.exit(1)
                if args.verbose:
                    print(result.stdout)
                    print(result.stderr)
                print(f"Rebooting {node.name}")
                # if we just reboot, the first reconnect attempt may erroneously
                # succeed before the box has actually shut down
                node.ssh.run("systemctl stop sshd && reboot")
                time.sleep(10)
            node.ssh.close()
            node.ssh_ready()
            cluster.k8s_ready()
            if args.nixos_action == "boot":
                try:
                    result = node.ssh.run(f"kubectl uncordon {node.name}")
                except UnexpectedExit as e:
                    print(e)
                    sys.exit(1)
                print(f"{node.name} uncordoned")
            list(map(cluster.daemonsets_ready, cluster.namespaces))
            list(map(cluster.deployments_ready, cluster.namespaces))
            cluster.ceph_ready()
            if args.upgrade:
                result = node.ssh.run("uname -r")
                final_kernel = result.stdout.strip()
                if final_kernel != initial_kernel:
                    print(
                        colored(
                            f"Kernel upgraded from {initial_kernel} to {final_kernel} on {node.name}",
                            "yellow",
                        )
                    )
    else:
        print(colored("No action needed on {}".format(node.name), "green"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--inventory", default="inventory.yaml")
    parser.add_argument("-n", "--nixos-action", default="boot")
    parser.add_argument("-u", "--upgrade", action="store_true")
    parser.add_argument("--skip-initial-health", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-d", "--disruption-budget", type=int)
    parser.add_argument("--private-key", type=str)
    args = parser.parse_args()

    if args.nixos_action != "boot" and args.nixos_action != "switch":
        raise AssertionError("--nixos-action must be one of boot, switch")

    cluster = Cluster.from_yaml(args)

    try:
        os.mkdir("artifacts")
    except FileExistsError:
        pass

    if not args.skip_initial_health:
        cluster.k8s_ready()
        list(map(cluster.daemonsets_ready, cluster.namespaces))
        list(map(cluster.deployments_ready, cluster.namespaces))
        cluster.ceph_ready()

    if args.disruption_budget:
        disruption_budget = args.disruption_budget
    else:
        disruption_budget = len(cluster.nodes) // 2

    with ThreadPoolExecutor(max_workers=disruption_budget) as pool:
        futures = {pool.submit(reconcile, n, cluster, args): n for n in cluster.nodes}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    print(result)
            except Exception:
                traceback.print_exc()
                sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
