"""
__main__.py

Purpose: Pulumi program for k8s-relay, an AWS Lightsail peer relay for the private network

Scope: One Lightsail instance and its public firewall ports

Overview: Creates the `k8s-relay` Lightsail instance in us-west-2 (the Lightsail region closest to
    the cluster). Cloud-init joins it to the tailnet as `tag:k8s-relay` and enables the peer relay
    server on UDP 40000. Devices that cannot reach each other directly relay through it instead of
    the shared DERP servers. The instance has a hard-coded physical name so `./run down` can delete
    it with the AWS CLI without Pulumi state; `./run up` uses throwaway state.

Dependencies: pulumi, pulumi-aws, AWS credentials (AWS_PROFILE), a tailnet auth key (config secret)

Exports: Stack output public_ip

Interfaces: Pulumi config keys authKey (secret), bundle

Implementation: The physical name is the contract with `./run down`; change both together
"""

import pulumi
import pulumi_aws as aws

NAME = "k8s-relay"  # physical name; `./run down` deletes by this name
REGION = "us-west-2"
AVAILABILITY_ZONE = "us-west-2a"
RELAY_PORT = 40000

config = pulumi.Config()
auth_key = config.require_secret("authKey")
# Relay throughput tracks the bundle's baseline network bandwidth, not CPU (see README).
bundle = config.get("bundle") or "large_3_0"

user_data = auth_key.apply(
    # Lightsail prepends its own init script and runs the result with sh, so stay POSIX.
    lambda key: f"""set -eux
curl -fsSL https://tailscale.com/install.sh | sh
tailscale up --auth-key='{key}' --hostname={NAME} --advertise-tags=tag:{NAME}
tailscale set --relay-server-port={RELAY_PORT} --auto-update
"""
)

provider = aws.Provider(f"aws-{REGION}", region=REGION)
opts = pulumi.ResourceOptions(provider=provider)

instance = aws.lightsail.Instance(
    NAME,
    name=NAME,
    availability_zone=AVAILABILITY_ZONE,
    blueprint_id="ubuntu_24_04",
    bundle_id=bundle,
    user_data=user_data,
    tags={"app": NAME},
    opts=opts,
)

aws.lightsail.InstancePublicPorts(
    f"{NAME}-ports",
    instance_name=instance.name,
    port_infos=[
        {"protocol": "udp", "from_port": RELAY_PORT, "to_port": RELAY_PORT},
        # SSH only from the Lightsail browser console.
        {"protocol": "tcp", "from_port": 22, "to_port": 22, "cidr_list_aliases": ["lightsail-connect"]},
    ],
    opts=opts,
)

pulumi.export("public_ip", instance.public_ip_address)
