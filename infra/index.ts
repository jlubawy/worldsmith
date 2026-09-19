import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as aws from "@pulumi/aws";
import * as pulumi from "@pulumi/pulumi";

const config = new pulumi.Config();
const name = config.get("name") ?? "minecraft";
const region = aws.config.region ?? "us-west-2";
const availabilityZone = config.get("availabilityZone") ?? `${region}a`;
// small_3_0 is the 2 GB / 2 vCPU plan ($12/mo). medium_3_0 is 4 GB ($24/mo),
// for running more than one world at a time or a large world.
const bundleId = config.get("bundleId") ?? "small_3_0";
// Who may SSH in. Key-only auth, so open is acceptable; narrow it to your
// home IP (e.g. 203.0.113.7/32) if you like.
const sshCidr = config.get("sshCidr") ?? "0.0.0.0/0";
const publicKeyPath = config.get("sshPublicKeyPath") ?? path.join(os.homedir(), ".ssh", "id_ed25519.pub");

const keyPair = new aws.lightsail.KeyPair(`${name}-key`, {
    name: `${name}-key`,
    publicKey: fs.readFileSync(publicKeyPath, "utf8").trim(),
});

// Runs once, as root, on first boot. `./mc cloud deploy` waits for it.
// Lightsail prepends its own #!/bin/sh script to this and runs the result
// with sh, so a shebang here is ignored: keep it POSIX (no pipefail, no [[).
const userData = `
set -eux

# The 2 GB plan has no swap; a little keeps world generation spikes from
# triggering the OOM killer.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

curl -fsSL https://get.docker.com | sh
usermod -aG docker ubuntu
systemctl enable --now docker

# Owned by ubuntu so the container (which runs as the owner of /data) and
# ./mc both read and write world files without sudo.
mkdir -p /opt/minecraft/data /opt/minecraft/backups
chown -R ubuntu:ubuntu /opt/minecraft
`;

const instance = new aws.lightsail.Instance(name, {
    name,
    availabilityZone,
    blueprintId: "ubuntu_24_04",
    bundleId,
    keyPairName: keyPair.name,
    userData,
    // Daily whole-disk snapshot, kept for 7 days (~$0.05/GB-month).
    // 10:00 UTC is 2-3 AM Pacific.
    addOn: { type: "AutoSnapshot", snapshotTime: "10:00", status: "Enabled" },
    tags: { app: "minecraft" },
}, {
    // Changing the launch script would replace the instance, and the world
    // lives on its disk. Edits to it only matter for a brand-new server.
    ignoreChanges: ["userData"],
});

const staticIp = new aws.lightsail.StaticIp(`${name}-ip`, { name: `${name}-ip` });

new aws.lightsail.StaticIpAttachment(`${name}-ip-attachment`, {
    staticIpName: staticIp.name,
    instanceName: instance.name,
});

// This replaces the instance's whole firewall, so SSH must be listed too.
// Bedrock's NetherNet transport: a TCP handshake on 19132, then gameplay over
// UDP on the range pinned by SERVER_UDP_PORTS in compose.yaml.
new aws.lightsail.InstancePublicPorts(`${name}-ports`, {
    instanceName: instance.name,
    portInfos: [
        { protocol: "tcp", fromPort: 22, toPort: 22, cidrs: [sshCidr] },
        { protocol: "tcp", fromPort: 19132, toPort: 19132, cidrs: ["0.0.0.0/0"], ipv6Cidrs: ["::/0"] },
        { protocol: "udp", fromPort: 19140, toPort: 19159, cidrs: ["0.0.0.0/0"], ipv6Cidrs: ["::/0"] },
    ],
}, {
    // Any change replaces this resource. The default create-then-delete order
    // makes the delete close every port the old and new sets share (SSH
    // included), so delete first; the ports are closed for a second or two.
    deleteBeforeReplace: true,
});

export const publicIp = staticIp.ipAddress;
export const instanceName = instance.name;
export const ssh = pulumi.interpolate`ssh ubuntu@${staticIp.ipAddress}`;
