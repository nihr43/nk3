import os
import time
import yaml
import json
import paramiko
import difflib
import uuid
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
        self.ssh_ready()

    def ssh_ready(self):
        i = 0
        while i < 300:
            i += 1
            if i % 5 == 0:
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
        raise NotImplementedError


if __name__ == "__main__":
    """
    for node in cluster.nodes:
        render configuration.nix
        if configuration.nix is different than renders/node/configuration.nix:
            write it
            scp it
            nixos-rebuild boot
            reboot it

        cluster.healthcheck()
    """
    yam = "inventory.yaml"
    cluster = Cluster.from_yaml(yam)

    file_loader = FileSystemLoader("templates/")
    env = Environment(loader=file_loader)
    template = env.get_template("configuration.nix")

    try:
        os.mkdir("artifacts")
    except FileExistsError:
        pass

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
            stdin, stdout, stderr = n.ssh.exec_command("nixos-rebuild boot")
            if stdout.channel.recv_exit_status() != 0:
                print(stdout.read().decode())
                print(stderr.read().decode())
                with n.sftp.open("/etc/nixos/configuration.nix", "w") as remote_file:
                    remote_file.write(remote_config_str)
                print(
                    "`nixos-rebuild boot` failed on {}.  Changes reverted".format(
                        n.name
                    )
                )
            else:
                print("Rebooting {}".format(n.name))
                n.ssh.exec_command("reboot")
                n.sftp.close()
                n.ssh.close()
                time.sleep(
                    10
                )  # ouch, it takes a moment for ssh to shut down in the first place
                n.ssh_ready()
                cluster.k8s_ready()
        else:
            print(colored("No action needed on {}".format(n.name), "green"))
