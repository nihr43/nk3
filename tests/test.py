import uuid
import time
import ipaddress
import pylxd
import json
import paramiko
import subprocess
from os import chmod
from Crypto.PublicKey import RSA


def create_keypair():
    """
    creates ssh keypair
    returns public key
    """
    key = RSA.generate(4096)
    with open("./private.key", "wb") as content_file:
        chmod("./private.key", 0o600)
        content_file.write(key.exportKey("PEM"))
    pubkey = key.publickey()
    with open("./public.key", "wb") as content_file:
        content_file.write(pubkey.exportKey("OpenSSH"))
    return pubkey


def get_nodes(client):
    """
    find instances
    """
    members = []
    for i in client.instances.all():
        try:
            js = json.loads(i.description)
            if js["nk3_node"]:
                members.append(i)
        except json.decoder.JSONDecodeError:
            continue
        except KeyError:
            continue

    if len(members) == 0:
        print("no nodes found")
    return members


def cleanup(client):
    instances_to_delete = get_nodes(client)

    for i in instances_to_delete:
        try:
            i.stop(wait=True)
        except pylxd.exceptions.LXDAPIException as e:
            try:
                if str(e) == "The instance is already stopped":
                    pass
            except TypeError as e:
                print("LXD -> incus todo:")
                print(e)
            pass
        i.delete(wait=True)
        print("{} deleted".format(i.name))


class MockNode:
    def __init__(self, client, sshkey, image):
        rnd = str(uuid.uuid4())[0:5]
        self.name = "nk3-{}".format(rnd)
        config = {
            "name": self.name,
            "description": '{"nk3_node": true}',
            "source": {
                "type": "image",
                "mode": "pull",
                "server": "https://images.linuxcontainers.org",
                "protocol": "simplestreams",
                "alias": image,
            },
            "config": {
                "limits.cpu": "4",
                "limits.memory": "8GB",
                "security.secureboot": "false",
            },
            "type": "virtual-machine",
        }

        self.inst = client.instances.create(config, wait=True)
        # TODO: no worky vms but worky containers?
        # self.inst.start(wait=True)
        subprocess.run(
            "incus start {}".format(self.name),
            shell=True,
            capture_output=True,
            text=True,
        )
        self.wait_until_ready()
        self.get_valid_ipv4("enp5s0")

        err = self.inst.execute(["mkdir", "-p", "/root/.ssh"])
        if err.exit_code != 0:
            raise RuntimeError(err.stderr)

        print("setting up ssh")
        self.inst.files.put("/root/.ssh/authorized_keys", sshkey.exportKey("OpenSSH"))
        # wow! subsequent reboots in network configuration were borking our ssh installation/configuration
        self.inst.execute(["sync"])

        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        private_key = paramiko.RSAKey.from_private_key_file("private.key")
        self.ssh.connect(self.ip, 22, "root", pkey=private_key)
        stdin, stdout, stderr = self.ssh.exec_command("hostname")
        print(stdout.read().decode())

    def wait_until_ready(self):
        """
        waits until an instance is executable
        """
        print("waiting for lxd agent to become ready on " + self.name)
        i = 0
        while i < 30:
            i += 1
            time.sleep(1)
            try:
                exit_code = self.inst.execute(["hostname"]).exit_code
            except BrokenPipeError:
                continue
            except ConnectionResetError:
                continue

            if exit_code == 0:
                return

        raise TimeoutError("timed out waiting")

    def get_valid_ipv4(self, interface):
        """
        ipv4 addresses can take a moment to be assigned on boot, so
        inst.state().network['eth0']['addresses'][0]['address'] is not reliable.
        This waits until a valid address is assigned and returns it.
        """
        print("waiting for valid ipv4 address on", self.name)
        i = 0
        while i < 30:
            i += 1
            time.sleep(1)
            candidate_ip = self.inst.state().network[interface]["addresses"][0][
                "address"
            ]
            try:
                ipaddress.IPv4Address(candidate_ip)
                print("found {} at {}".format(self.name, candidate_ip))
                self.ip = candidate_ip
            except ipaddress.AddressValueError:
                continue
            except ConnectionResetError:
                continue
            return

        raise TimeoutError("timed out waiting")


if __name__ == "__main__":
    client = pylxd.Client(endpoint="/var/lib/incus/unix.socket")
    cleanup(client)
    pubkey = create_keypair()
    nodes = []

    for n in range(3):
        node = MockNode(client, pubkey, "nixos/23.11")
        nodes.append(node)
