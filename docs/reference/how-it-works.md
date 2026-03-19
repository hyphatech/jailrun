---
icon: material/layers-outline
---

# How it works

Jailrun is an orchestration layer. It doesn't reinvent any of the underlying tools — it wires together a set of proven, focused components, each chosen for a reason.

## The stack

| Layer               | Tool                                                                                                  | Role                                                                                  |
|---------------------|-------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| OS                  | [FreeBSD](https://www.freebsd.org)                                                                    | Provides the base system, jail isolation, ZFS, pf, and the userland Jailrun builds on |
| Virtual machine     | [QEMU](https://www.qemu.org/)                                                                         | Runs FreeBSD with hardware acceleration (HVF on macOS, KVM on Linux, TCG on FreeBSD)  |
| Jail management     | [Bastille](https://bastillebsd.org/)                                                                  | Creates, destroys, and manages jail lifecycles                                        |
| Provisioning        | [Ansible](https://docs.ansible.com/)                                                                  | Runs playbooks to install software inside jails and the VM                            |
| Configuration       | [UCL](https://github.com/vstakhov/libucl)                                                             | Human-friendly config format, native to FreeBSD                                       |
| Process supervision | [monit](https://mmonit.com/monit/)                                                                    | Monitors processes inside jails, restarts on failure, runs healthchecks               |
| Filesystem          | [ZFS](https://docs.freebsd.org/en/books/handbook/zfs/) + [9p](https://wiki.qemu.org/Documentation/9p) | Instant jail clones via ZFS snapshots; host directory sharing via 9p                  |
| Networking          | [pf](https://docs.freebsd.org/en/books/handbook/firewalls/#firewalls-pf)                              | FreeBSD's packet filter handles port forwarding between host and jails                |

Every component is transparent and accessible. You can inspect, modify, and extend any layer.

## Lifecycle

Four commands control the entire lifecycle:

``` mermaid
graph LR
  START["jrun start"] --> UP["jrun up"]
  UP --> DOWN["jrun down"]
  DOWN --> STOP["jrun stop"]
```

### `jrun start`

Boots FreeBSD on your host inside QEMU. On first run it downloads the image and provisions SSH access. If a base config is provided, it runs VM-level playbooks.

### `jrun up`

Reads your config, resolves the dependency graph, and deploys each jail in order. If the port forwarding or mount configuration changed since the last deploy, `jrun` automatically restarts the VM to apply the new wiring.

### `jrun down`

Removes a jail and cleans up its mounts, ports, DNS entries, and processes without affecting the rest of the stack.

### `jrun stop`

Shuts down the FreeBSD VM gracefully. The VM image and jail state are preserved on disk — `jrun start` will boot from where you left off.

## Platform support

| Platform                             | Architecture  | Acceleration | Status   |
|--------------------------------------|---------------|--------------|----------|
| :fontawesome-brands-apple: macOS     | Apple Silicon | HVF          | Tested   |
| :fontawesome-brands-apple: macOS     | Intel         | HVF          | Untested |
| :fontawesome-brands-linux: Linux     | x86_64        | KVM          | Tested   |
| :fontawesome-brands-linux: Linux     | aarch64       | KVM          | Untested |
| :fontawesome-brands-freebsd: FreeBSD | x86_64        | TCG          | Tested   |
| :fontawesome-brands-freebsd: FreeBSD | aarch64       | TCG          | Untested |
