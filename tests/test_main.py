import uuid
import time
import ipaddress
import logging
import pylxd
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
            "config": {"limits.cpu": "2", "limits.memory": "1GB"},
            "type": "virtual-machine",
        }

        self.inst = client.instances.create(config, wait=True)
        self.inst.start(wait=True)
#        self.wait_until_ready()
#        self.get_valid_ipv4("eth0")

#        err = self.inst.execute(
#            [pkgm, "install", "python3", "openssh-server", "ca-certificates", "-y"]
#        )
        if err.exit_code != 0:
            raise RuntimeError(err.stderr)
        err = self.inst.execute(["mkdir", "-p", "/root/.ssh"])
        if err.exit_code != 0:
            raise RuntimeError(err.stderr)

        self.inst.files.put("/root/.ssh/authorized_keys", sshkey.exportKey("OpenSSH"))
        # wow! subsequent reboots in network configuration were borking our ssh installation/configuration
        self.inst.execute(["sync"])

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
            except ipaddress.AddressValueError:
                continue
            except ConnectionResetError:
                continue
            else:
                return candidate_ip

        raise TimeoutError("timed out waiting")



client = pylxd.Client(endpoint="/var/lib/incus/unix.socket")
pubkey = create_keypair()
memes = MockNode(client, pubkey, 'nixos/23.11')
