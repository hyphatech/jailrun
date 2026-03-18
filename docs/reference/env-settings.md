---
icon: material/variable
---

# Environment settings

All settings have sensible defaults. Override them with environment variables or place them in a `.env` file in your project root.

To use a custom env file:

```bash
JRUN_ENV_FILE=/path/to/.env jrun start
```

## VM

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_SSH_PORT` | `2222` | Host port for VM SSH |
| `JRUN_SSH_USER` | `admin` | SSH user for the VM |
| `JRUN_SSH_KEY` | `id_ed25519` | SSH key name |
| `JRUN_VM_HOST` | `127.0.0.1` | VM host address |
| `JRUN_VM_PYTHON_INTERPRETER` | `python3.13` | Python interpreter inside the VM |

## QEMU

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_QEMU_MEMORY` | `4096M` | VM memory allocation |
| `JRUN_QEMU_DISK_SIZE` | `20G` | VM disk size |
| `JRUN_QEMU_CPUS` | auto | Number of CPUs (uses all available if not set) |
| `JRUN_QEMU_BIOS` | auto | Custom BIOS path |

## FreeBSD

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_BSD_VERSION` | `15.0` | FreeBSD version |
| `JRUN_BSD_RELEASE_TAG` | `RELEASE` | FreeBSD release tag |
| `JRUN_BSD_ARCH` | auto-detected | Architecture (`aarch64` or `amd64`) |

## Networking

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_MESH_NETWORK` | `true` | Enable Yggdrasil mesh networking between jails |

## Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_SSH_DIR` | `~/.jrun/ssh` | SSH keys directory |
| `JRUN_LOG_DIR` | `~/.jrun/logs` | Log files directory |
| `JRUN_DISK_DIR` | `~/.jrun/disks` | VM disk images directory |
| `JRUN_CLOUD_DIR` | `~/.jrun/cloud-init` | Cloud-init config directory |
| `JRUN_PLAYBOOK_CACHE_DIR` | `~/.jrun/playbooks` | Cached Hub playbooks |
| `JRUN_STATE_FILE` | `~/.jrun/state.json` | VM state file |
| `JRUN_PID_FILE` | `~/.jrun/vm.pid` | VM process ID file |
