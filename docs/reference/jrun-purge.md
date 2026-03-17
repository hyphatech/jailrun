# jrun purge

Stop and destroy the VM with all jails.

```bash
jrun purge
```

This shuts down the VM, removes the FreeBSD image, and deletes all jail state. A fresh `jrun start` after this will download the image and provision from scratch.

!!! warning

    This is destructive and irreversible. All jail data, snapshots, and provisioning state will be lost.
