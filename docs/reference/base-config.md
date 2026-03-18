---
icon: material/file-code-outline
---

# Base config

A base config defines VM-level settings — provisioning, shared directories, and port forwards that apply to the FreeBSD VM itself, not to individual jails.

Pass it to `jrun start` or `jrun up` with the `--base` flag:

```bash
jrun start --base base.ucl
```

## Full example

```
base {
  setup {
    provision { type = "ansible"; file = "base-setup.yml"; }
  }
  mount {
    data { host = "./data"; target = "/home/admin/data"; }
  }
  forward {
    custom_ssh { proto = "tcp"; host = 2200; target = 22; }
  }
}
```

## Blocks

### `setup`

Ansible playbooks that run against the VM itself. Use this for system-wide configuration — installing packages, setting up users, or provisioning a graphical desktop.

```
setup {
  provision { type = "ansible"; file = "base-setup.yml"; }
  desktop {
    type = "ansible";
    url  = "hub://xfce/rolling";
    vars { X_RESOLUTION = "1920x1080"; }
  }
}
```

Playbooks run in the order they're defined. You can mix local playbooks with [Jailrun Hub](https://github.com/hyphatech/jailrun-hub) playbooks, same as with jail configs.

To re-run VM provisioning:

```bash
jrun start --provision
```

### `mount`

Share directories from your host into the VM.

```
mount {
  data { host = "./data"; target = "/home/admin/data"; }
}
```

### `forward`

Forward ports from your host to the VM (not to jails — use jail configs for that).

```
forward {
  custom_ssh { proto = "tcp"; host = 2200; target = 22; }
}
```
