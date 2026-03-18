# jrun start

Boot the FreeBSD VM.

```bash
jrun start
```

On first run, jrun downloads a FreeBSD image, boots it with hardware acceleration, and provisions SSH access. Subsequent runs boot instantly from the existing image.

## Options

### `--base` { #base }

Apply a base config to the VM:

```bash
jrun start --base base.ucl
```

Base configs define VM-level provisioning, mounts, and port forwards. See [Base config](base-config.md) for the full reference.

### `--provision` { #provision }

Re-run base provisioning on an already-booted VM:

```bash
jrun start --provision
```

Useful after editing your base config or its playbooks without restarting the VM.

### `--mode` { #mode }

Boot the VM with a specific display mode:

```bash
jrun start --mode graphic
```

Opens a QEMU window with mouse and keyboard support. Useful for running graphical desktops or debugging boot issues. The default mode is headless.
