import os
import sys
import time
import yaml
import json
import paramiko
import difflib
import uuid
import argparse
from termcolor import colored
from jinja2 import Environment, FileSystemLoader


class Cluster:
    def __init__(self, join_address, join_token, nodes, default_gateway):
        self.join_address = join_address
        self.join_token = join_token
        self.nodes = nodes
        self.default_gateway = default_gateway

    @classmethod
    def from_yaml(cls, file_path):
        with open(file_path, "r") as file:
            data = yaml.safe_load(file)
            cluster_data = data["cluster"]
            join_address = cluster_data["join_address"]
            join_token = cluster_data["join_token"]
            default_gateway = cluster_data["default_gateway"]
            nodes = []
            for n, d in cluster_data["nodes"].items():
                nodes.append(Node(n, d["initiator"], d["interface"], d["boot_device"]))
            return cls(join_address, join_token, nodes, default_gateway)

    def k8s_ready(self):
        for n in self.nodes:
            n.k8s_ready()


class Node:
    def __init__(self, ip, initiator, interface, boot_device):
        self.ip = ip
        self.boot_device = boot_device
        self.interface = interface
        self.initiator = initiator
        self.name = uuid.uuid5(uuid.NAMESPACE_OID, self.ip)
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.private_key = paramiko.RSAKey.from_private_key_file("private.key")
        self.ssh.connect(self.ip, 22, "root", pkey=self.private_key)
        self.sftp = self.ssh.open_sftp()
        self.ssh_ready()

    def ssh_ready(self):
        i = 0
        while i < 300:
            i += 1
            if i % 10 == 0:
                print("Waiting for {} become reachable".format(self.name))
            try:
                self.ssh.exec_command("hostname")
                print("{} is reachable".format(self.name))
                return
            except AttributeError:
                time.sleep(1)
                try:
                    self.ssh.connect(self.ip, 22, "root", pkey=self.private_key)
                    self.sftp = self.ssh.open_sftp()
                except (paramiko.ssh_exception.NoValidConnectionsError, TimeoutError):
                    continue
            except paramiko.ssh_exception.SSHException:
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
        while i < 300:
            i += 1
            stdin, stdout, stderr = self.ssh.exec_command(
                "kubectl -n rook-ceph get cephcluster rook-ceph -o jsonpath='{.status.ceph.health}'"
            )
            health = stdout.read().decode()
            if i % 10 == 0 and health != "HEALTH_OK":
                print(f"ceph state is {health}")
            if health == "HEALTH_OK":
                print(f"ceph state is {health}")
                return
            else:
                time.sleep(1)

        raise TimeoutError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--inventory", default="inventory.yaml")
    parser.add_argument("-n", "--nixos-action", default="boot")
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

    #    cluster.k8s_ready()

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
            print("Rebuilding NixOS on {}".format(n.name))
            stdin, stdout, stderr = n.ssh.exec_command(
                f"nixos-rebuild {args.nixos_action}"
            )
            if stdout.channel.recv_exit_status() != 0:
                print(stdout.read().decode())
                print(stderr.read().decode())
                with n.sftp.open("/etc/nixos/configuration.nix", "w") as remote_file:
                    remote_file.write(remote_config_str)
                print(f"`nixos-rebuild` failed on {n.name}.  Changes reverted")
            else:
                if args.nixos_action == "boot":
                    print(f"Rebooting {n.name}")
                    # if we just reboot, the first reconnect attempt may erroneously
                    # succeed before the box has actually shut down
                    n.ssh.exec_command("systemctl stop sshd && reboot")
                n.sftp.close()
                n.ssh.close()
                n.ssh_ready()
                cluster.k8s_ready()
                n.ceph_ready()
        else:
            print(colored("No action needed on {}".format(n.name), "green"))


if __name__ == "__main__":
    sys.exit(main())
