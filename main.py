import os
import sys
import time
import yaml
import json
import paramiko
import difflib
import uuid
import argparse
import traceback
import logging
import ipaddress
from termcolor import colored
from jinja2 import Environment, FileSystemLoader
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.getLogger("paramiko").setLevel(logging.CRITICAL)


class Cluster:
    def __init__(self, join_address, join_token, nodes, nix_channel):
        self.join_address = join_address
        self.join_token = join_token
        self.nodes = nodes
        self.nix_channel = nix_channel

    @classmethod
    def from_yaml(cls, file_path):
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
            join_address = data["join_address"]
            join_token = data["join_token"]
            nix_channel = data["nix_channel"]
            nodes = []
            for n, d in data["nodes"].items():
                nodes.append(Node(n, d["initiator"], d["boot_device"]))
            return cls(join_address, join_token, nodes, nix_channel)

    def k8s_ready(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(n.k8s_ready): n for n in self.nodes}

        for future in as_completed(futures):
            try:
                result = future.result()
                if result:
                    print(result)
            except Exception:
                traceback.print_exc()
                sys.exit(1)

    def ceph_ready(self):
        self.nodes[0].ceph_ready()


class Node:
    def __init__(self, ip, initiator, boot_device):
        self.ip = ip
        self.boot_device = boot_device
        self.initiator = initiator
        self.name = uuid.uuid5(uuid.NAMESPACE_OID, self.ip)
        self.ssh_ready()
        self.interface = self.get_interface()
        self.gateway = self.get_gateway()

    def get_interface(self):
        stdin, stdout, stderr = self.ssh.exec_command(
            "ip r get 1.1.1.1 | awk '/via/{print $5}'"
        )
        interface = stdout.read().decode().strip()
        if interface.startswith(("eth", "eno", "enp")):
            return interface
        else:
            raise NotImplementedError(interface)

    def get_gateway(self):
        stdin, stdout, stderr = self.ssh.exec_command(
            "ip r get 1.1.1.1 | awk '/via/{print $3}'"
        )
        gw = stdout.read().decode().strip()
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
                print("Waiting for {} become reachable".format(self.name))
            try:
                self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                self.ssh.connect(self.ip, 22, "root")
                self.sftp = self.ssh.open_sftp()
                self.ssh.exec_command("hostname")
                print("{} is reachable".format(self.name))
                return
            except AttributeError:
                self.ssh = paramiko.SSHClient()
                continue
            except (
                paramiko.ssh_exception.SSHException,
                paramiko.ssh_exception.NoValidConnectionsError,
                TimeoutError,
                EOFError,
            ):
                time.sleep(1)
                continue

        raise TimeoutError

    def k8s_ready(self):
        i = 0
        while i < 300:
            i += 1
            try:
                stdin, stdout, stderr = self.ssh.exec_command(
                    "kubectl get node {} -o json".format(self.name)
                )
                node_json = json.loads(stdout.read().decode())
                for condition in node_json["status"]["conditions"]:
                    if (
                        condition["reason"] == "KubeletReady"
                        and condition["status"] == "True"
                    ):
                        print(colored("k8s is ready on {}".format(self.name), "green"))
                        return
                    elif (
                        condition["reason"] == "KubeletReady"
                        and condition["status"] == "False"
                    ):
                        print("k8s is not ready on {}".format(self.name))
                        time.sleep(1)
                        continue
            except json.decoder.JSONDecodeError:
                time.sleep(1)
                continue

        raise TimeoutError

    def ceph_ready(self):
        i = 0
        while i < 600:
            i += 1
            stdin, stdout, stderr = self.ssh.exec_command(
                "kubectl -n rook-ceph exec deployment/rook-ceph-tools --pod-running-timeout=5m -- ceph status -f json"
            )
            try:
                js = json.loads(stdout.read().decode())
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--inventory", default="inventory.yaml")
    parser.add_argument("-n", "--nixos-action", default="boot")
    parser.add_argument("-u", "--upgrade", action="store_true")
    parser.add_argument("--skip-initial-health", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.nixos_action != "boot" and args.nixos_action != "switch":
        raise AssertionError("--nixos-action must be one of boot, switch")

    cluster = Cluster.from_yaml(args.inventory)

    file_loader = FileSystemLoader("templates/")
    env = Environment(loader=file_loader)
    template = env.get_template("configuration.nix")

    try:
        os.mkdir("artifacts")
    except FileExistsError:
        pass

    if not args.skip_initial_health:
        cluster.k8s_ready()
        cluster.ceph_ready()

    for n in cluster.nodes:
        output = template.render(node=n, cluster=cluster)

        output_file_path = "artifacts/{}".format(n.name)
        with open(output_file_path, "w") as f:
            f.write(output)

        with open(output_file_path, "r") as local_file:
            local_config = local_file.readlines()

        with n.sftp.file("/etc/nixos/configuration.nix", "r") as remote_file:
            remote_config = remote_file.readlines()
            remote_file.seek(0)
            remote_config_str = remote_file.read()

        diff = list(difflib.unified_diff(remote_config, local_config))
        diff_formatted = colored("".join(diff).strip(), "yellow")

        if diff:
            print("{} modified:".format(n.name))
            print(diff_formatted)
            n.sftp.put(output_file_path, "/etc/nixos/configuration.nix")

        if diff or args.upgrade:
            print("Rebuilding NixOS on {}".format(n.name))
            if args.upgrade:
                channel_cmd = f"nix-channel --add https://nixos.org/channels/{cluster.nix_channel} nixos"
                stdin, stdout, stderr = n.ssh.exec_command(channel_cmd)
                if stdout.channel.recv_exit_status() != 0:
                    print(stdout.read().decode())
                    print(stderr.read().decode())
                    raise RuntimeError
                nixos_cmd = f"nixos-rebuild {args.nixos_action} --upgrade"
            else:
                nixos_cmd = f"nixos-rebuild {args.nixos_action}"
            stdin, stdout, stderr = n.ssh.exec_command(nixos_cmd)

            if stdout.channel.recv_exit_status() != 0:
                print(stdout.read().decode())
                print(stderr.read().decode())
                with n.sftp.open("/etc/nixos/configuration.nix", "w") as remote_file:
                    remote_file.write(remote_config_str)
                print(f"`nixos-rebuild` failed on {n.name}.  Changes reverted")
                raise RuntimeError()
            else:
                if args.verbose:
                    print(stdout.read().decode())
                    print(stderr.read().decode())
                if args.nixos_action == "boot":
                    print(f"Draining {n.name}")
                    stdin, stdout, stderr = n.ssh.exec_command(
                        f"kubectl drain {n.name} --ignore-daemonsets --delete-emptydir-data"
                    )
                    if stdout.channel.recv_exit_status() != 0:
                        print(stdout.read().decode())
                        print(stderr.read().decode())
                        raise RuntimeError()
                    if args.verbose:
                        print(stdout.read().decode())
                        print(stderr.read().decode())
                    print(f"Rebooting {n.name}")
                    # if we just reboot, the first reconnect attempt may erroneously
                    # succeed before the box has actually shut down
                    n.ssh.exec_command("systemctl stop sshd && reboot")
                n.sftp.close()
                n.ssh.close()
                n.ssh_ready()
                cluster.k8s_ready()
                if args.nixos_action == "boot":
                    stdin, stdout, stderr = n.ssh.exec_command(
                        f"kubectl uncordon {n.name}"
                    )
                    if stdout.channel.recv_exit_status() != 0:
                        print(stdout.read().decode())
                        print(stderr.read().decode())
                        raise RuntimeError()
                    print(f"{n.name} uncordoned")
                cluster.ceph_ready()
        else:
            print(colored("No action needed on {}".format(n.name), "green"))


if __name__ == "__main__":
    sys.exit(main())
