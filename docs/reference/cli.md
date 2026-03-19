---
icon: material/console
---

# CLI reference

`jrun` is a modern CLI with an interactive shell, command autocomplete, and a minimal, well-thought set of commands. Everything you need, nothing you don't.

| Command | Description |
|---------|-------------|
| [`jrun`](jrun-interactive.md) | Interactive shell |
| [`jrun start`](jrun-start.md) | Boot the VM (downloads FreeBSD on first run) |
| [`jrun start --base <config>`](jrun-start.md#base) | Boot the VM with a base config applied |
| [`jrun start --provision`](jrun-start.md#provision) | Re-run base provisioning on an already-booted VM |
| [`jrun start --mode graphic`](jrun-start.md#mode) | Boot the VM with a graphical QEMU display |
| [`jrun stop`](jrun-stop.md) | Shut down the VM gracefully |
| [`jrun ssh`](jrun-ssh.md) | SSH into the VM |
| [`jrun ssh <n>`](jrun-ssh.md#jail) | SSH directly into a jail |
| [`jrun cmd`](jrun-cmd.md) | Run a command inside a jail |
| [`jrun up`](jrun-up.md) | Create or update all jails in a config |
| [`jrun up <config> <name...>`](jrun-up.md#specific) | Deploy specific jails (dependencies included automatically) |
| [`jrun pause`](jrun-pause.md) | Interactively select existing jails to stop without destroying them |
| [`jrun pause <name...>`](jrun-pause.md#specific) | Stop specific existing jails without destroying them |
| [`jrun down`](jrun-down.md) | Interactively select existing jails to destroy |
| [`jrun down <name...>`](jrun-down.md#specific) | Destroy specific jails |
| [`jrun status`](jrun-status.md) | Show VM and jail status |
| [`jrun status --tree`](jrun-status.md#tree) | Show VM and jail status as a tree |
| [`jrun snapshot create <jail>`](jrun-snapshot.md) | Create a snapshot with auto-generated name |
| [`jrun snapshot create <jail> <name>`](jrun-snapshot.md#named) | Create a named snapshot |
| [`jrun snapshot list <jail>`](jrun-snapshot.md#list) | List snapshots for a jail |
| [`jrun snapshot rollback <jail> <name>`](jrun-snapshot.md#rollback) | Rollback a jail to a snapshot |
| [`jrun snapshot delete <jail> <name>`](jrun-snapshot.md#delete) | Delete a snapshot |
| [`jrun purge`](jrun-purge.md) | Stop and destroy the VM with all jails |
