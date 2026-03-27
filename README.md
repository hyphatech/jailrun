# Jailrun

Jailrun lets you describe your services in a declarative config file and brings the system to the desired state. Under the hood, it boots a FreeBSD virtual machine on your host using QEMU with hardware acceleration to provision each service in its own jail, and exposes a set of powerful tools to wire and manage them.

<p align="center">
  <img src="https://raw.githubusercontent.com/hyphatech/jailrun/main/screenshot.png" alt="screenshot" width="100%" />
</p>

## What is a jail?

A jail is a self-contained environment running inside FreeBSD. Each jail is isolated from the host and from other jails, with its own filesystem, network, and processes.

Jails are a native FreeBSD feature. They are fast to create, cheap to run, and easy to destroy and recreate from scratch. FreeBSD jails are one of the most proven isolation technologies in computing, and Jailrun makes them accessible from macOS, Linux, and FreeBSD itself.

## Install

**macOS (Homebrew):**

```bash
brew tap hyphatech/jailrun
brew install jailrun
```

This installs `jrun` and all its dependencies — Python, QEMU, Ansible, and mkisofs.

**Linux:**

Install the system-level dependencies first:

```bash
# Debian/Ubuntu
sudo apt install qemu-system mkisofs ansible

# Fedora
sudo dnf install qemu-system-x86 genisoimage ansible

# Arch
sudo pacman -S qemu-full cdrtools ansible
```

Install Python 3.13+ using your operating system's package manager or preferred installation method.

Install uv using your distribution's package manager if available, or via the official installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then `jrun` itself:

```bash
uv tool install jailrun
```

To install `jrun` directly from the latest source on `main`:

```bash
uv tool install "git+https://github.com/hyphatech/jailrun.git@main"
```

**FreeBSD:**

Install the host dependencies first:

```bash
pkg install qemu edk2-qemu-x64 uv rust cdrtools python313
```

Some Python dependencies may not have prebuilt wheels on FreeBSD and may need to be compiled locally, so `rust` is required.

Install Ansible and jrun with Python 3.13:

```bash
uv tool install --python 3.13 --with-executables-from ansible-core ansible
uv tool install --python 3.13 jailrun
```

To install jrun directly from the latest source on main:

```bash
uv tool install --python 3.13 "git+https://github.com/hyphatech/jailrun.git@main"
```

If jrun is not found after installation, make sure uv's user bin directory is on your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Quick start

Bring FreeBSD to your system:

```bash
jrun start
```

On first run, jrun downloads the FreeBSD image and bootstraps the base system.

Prefer an interactive experience? Run `jrun` with no arguments to enter the shell — guided wizards, autocomplete, and command history all included.

```bash
jrun
```

## Your first jail

Jails are defined in config files using [UCL](https://github.com/vstakhov/libucl) — a clean, human-friendly format similar to JSON.

Create a file called `web.ucl` in your project directory:

```
jail "http-server" {
  forward {
    http { host = 7777; jail = 8080; }
  }
  mount {
    src { host = "."; jail = "/srv/project"; }
  }
  exec {
    server {
      cmd = "python3.13 -m http.server 8080";
      dir = "/srv/project";
    }
  }
}
```

Bring it up:

```bash
jrun up web.ucl
```

Here's what's happening:

- **A jail was created** — a fully isolated environment with its own IP address and filesystem.
- **Your project directory was mounted** inside the jail at `/srv/project`. Changes you make on your host show up instantly inside the jail, and vice versa.
- **Port 7777 on your host** was forwarded to port 8080 inside the jail. Traffic flows through automatically.
- **A Python HTTP server was started** inside the jail, serving your project files. It's supervised — if it crashes, it gets restarted.

Test it:

```bash
curl -sS localhost:7777
```

One config file, one command, and you can safely interact with your app from the host.

## A real-world stack

Here's something more realistic: a FastAPI application running on Python 3.14, backed by PostgreSQL. Three jails, each doing one thing, all wired together.

```
# stack.ucl

jail "python-314" {
  setup {
    python { type = "ansible"; file = "playbooks/python-314.yml"; }
  }
}

jail "postgres-16" {
  setup {
    postgres { type = "ansible"; file = "playbooks/postgres.yml"; }
  }
  forward {
    pg { host = 6432; jail = 5432; }
  }
}

jail "fastapi-314" {
  base { type = "jail"; name = "python-314"; }

  depends ["postgres-16"]

  setup {
    fastapi { type = "ansible"; file = "playbooks/fastapi-314.yml"; }
  }
  forward {
    http { host = 8080; jail = 8000; }
  }
  mount {
    src { host = "."; jail = "/srv/app"; }
  }
  exec {
    uvicorn {
      cmd = "python3.14 -m uvicorn app:app --reload --host 0.0.0.0";
      dir = "/srv/app";
      healthcheck {
        test = "fetch -qo /dev/null http://127.0.0.1:8000";
        interval = "30s";
        timeout = "10s";
        retries = 5;
      }
    }
  }
}
```

Bring all services up together:

```bash
jrun up stack.ucl
```

Here's what's happening:

- **Each `setup` block points to an Ansible playbook** that runs when the jail is first created. `python-314` compiles Python 3.14 from source. `postgres-16` installs and configures PostgreSQL.

- **Block `base` clones one jail from another.** Compiling from source might be slow. You do it once in `python-314`, then `fastapi-314` is created as a ZFS clone — a fully independent copy ready in milliseconds, using no extra disk space until it diverges from the base.

- **Block `depends` controls deploy order.** jrun resolves the dependency graph automatically. In this case: `python-314` first (it's the base), then `postgres-16` (it's a dependency), then `fastapi-314` last.

- **Jails discover each other by name.** From inside `fastapi-314`, you can `ping postgres-16.local.jrun` — it just works. Use jail names directly in your app's database config.

- **Port forwarding works from your host.** PostgreSQL is reachable at `localhost:6432`. Your FastAPI app is at `localhost:8080`. Healthchecks are built in — the process supervisor monitors it and restarts it if the check fails.

- **Live reload works out of the box.** Your project directory is shared into the jail. Uvicorn's `--reload` sees file changes instantly.

Check on everything:

```bash
$ jrun status

  ● VM  running  on 127.0.0.1:2222  (pid 98136)

  uptime     7:10PM  up 15 mins, 0 users, load averages: 1.04, 0.91, 0.85
  disk       9.9G free of 13G
  memory     2.0 GB usable / 4.0 GB total

  name           state    ports           mounts
  fastapi-314    up       tcp/8080→8000   …/examples/fastapi → /srv/app
  postgres-16    up       tcp/6432→5432   —
  python-314     up       —               —
```

Drop into any jail to debug or inspect:

```bash
jrun ssh postgres-16
```

Run a command inside a jail without opening a shell:

```bash
jrun cmd postgres-16 psql -U postgres -c 'SELECT version()'
```

## Using shared playbooks

Not every playbook needs to be written from scratch. [Jailrun Hub](https://hub.jail.run) is a curated collection of ready-to-use playbooks for common services — Redis, Nginx, PostgreSQL, and more.

Point a setup step at a Hub playbook with `url` instead of `file`:

```
jail "nginx" {
  setup {
    nginx {
      type = "ansible";
      url  = "hub://nginx/rolling";
      vars { NGINX_LISTEN_PORT = "88"; }
    }
  }
  forward {
    http { host = 8888; jail = 88; }
  }
}
```

The shorthand is equivalent to a full URL:

```
jail "nginx" {
  setup {
    nginx {
      type = "ansible";
      url  = "https://github.com/hyphatech/jailrun-hub/blob/main/playbooks/nginx/rolling/playbook.yml";
      vars { NGINX_LISTEN_PORT = "88"; }
    }
  }
  forward {
    http { host = 8888; jail = 88; }
  }
}
```

Both forms support pinning to a tag for reproducible builds:

```
url = "hub://nginx/rolling@v1.0.0";
```

```
url = "https://github.com/hyphatech/jailrun-hub/blob/v1.0.0/playbooks/nginx/rolling/playbook.yml";
```

Use `vars` to pass variables into the playbook — each playbook documents what it accepts. Works the same way with local ones:

```
setup {
  core { type = "ansible"; file = "setup.yml"; vars { APP_ENV = "production"; } }
}
```

## Updating and tearing down

To redeploy a single jail after changing its config:

```bash
jrun up stack.ucl fastapi-314
```

To tear down specific jails:

```bash
jrun down python-314
```

Other jails are left untouched. To interactively select jails to destroy:

```bash
jrun down
```

## Documentation

Full documentation is available at [jail.run](https://jail.run/).

## Commands

| Command                                                             | Description                                                 |
|---------------------------------------------------------------------|-------------------------------------------------------------|
| `jrun`                                                              | Interactive shell                                           |
| `jrun start`                                                        | Boot the VM (downloads FreeBSD on first run)                |
| `jrun start --base <config>`                                        | Boot the VM with a base config applied                      |
| `jrun start --provision`                                            | Re-run base provisioning on an already-booted VM            |
| `jrun start --mode graphic`                                         | Boot the VM with a graphical QEMU display                   |
| `jrun stop`                                                         | Shut down the VM gracefully                                 |
| `jrun ssh`                                                          | SSH into the VM                                             |
| `jrun ssh <n>`                                                      | SSH directly into a jail                                    |
| `jrun cmd`                                                          | Run a command inside a jail                                 |
| `jrun up`                                                           | Create or update all jails in a config                      |
| `jrun up <config> <name...>`                                        | Deploy specific jails (dependencies included automatically) |
| `jrun down`                                                         | Interactively select existing jails to destroy              |
| `jrun down <name...>`                                               | Destroy specific jails                                      |
| `jrun status`                                                       | Show VM and jail status                                     |
| `jrun status --show <col>`                                          | Add extra columns: `ip`, `services`, `all`                  |
| `jrun status --tree`                                                | Render status as a tree                                     |
| `jrun status <jail>`                                                | Full detail view for a single jail                          |
| `jrun status <jail> --live`                                         | Live service monitor with sparklines                        |
| `jrun snapshot create <jail>`                                       | Create a snapshot with auto-generated name                  |
| `jrun snapshot create <jail> <name>`                                | Create a named snapshot                                     |
| `jrun snapshot list <jail>`                                         | List snapshots for a jail                                   |
| `jrun snapshot rollback <jail> <name>`                              | Rollback a jail to a snapshot                               |
| `jrun snapshot delete <jail> <name>`                                | Delete a snapshot                                           |
| `jrun pair`                                                         | Create a mesh pairing and get a code                        |
| `jrun pair <code>`                                                  | Join a pairing using a peer's code                          |
| `jrun pair --list`                                                  | List current pairings                                       |
| `jrun pair --drop <code>`                                           | Remove a pairing and revoke access                          |
| `jrun purge`                                                        | Stop and destroy the VM with all jails                      |

## Config reference

### Jail config

A jail config file defines one or more jails. Each jail can have mounts, port forwards, setup playbooks, and supervised processes.

```
jail "myapp" {
  # FreeBSD release (optional, defaults to the VM's version)
  release = "15.0-RELEASE";

  # Static IP address (optional, auto-assigned if omitted)
  ip = "10.17.89.50";

  # Clone from an existing jail instead of creating from scratch
  base { type = "jail"; name = "base-jail"; }

  # Other jails that must exist before this one is deployed
  depends ["postgres", "redis"]

  # Share directories from your host into the jail
  mount {
    src { host = "."; jail = "/srv/app"; }
    data { host = "./data"; jail = "/var/data"; }
  }

  # Forward ports from your host to the jail
  forward {
    http { host = 8080; jail = 8080; }
    debug { host = 9229; jail = 9229; }
  }

  # Supervised processes (monitored, auto-restarted on failure)
  exec {
    server {
      cmd = "gunicorn app:main -b 0.0.0.0:8080";
      dir = "/srv/app";
      env {
        DATABASE_URL = "postgresql://postgres-16.local.jrun:5432/mydb";
        APP_ENV = "production";
      }
      healthcheck {
        test = "fetch -qo /dev/null http://127.0.0.1:8080/health";
        interval = "30s";
        timeout = "10s";
        retries = 5;
      }
    }
    worker {
      cmd = "python3 worker.py";
      dir = "/srv/app";
    }
  }

  # Ansible playbooks for provisioning, run in order
  setup {
    core { type = "ansible"; file = "install-deps.yml"; }
    extras { type = "ansible"; file = "install-more-deps.yml"; vars { DEBUG = "true"; } }
    nginx {
      type = "ansible";
      url  = "hub://nginx/rolling";
      vars { NGINX_LISTEN_PORT = "80"; }
    }
  }
}
```

### Base config

Optional VM-level config for customizing the base system. Passed to `jrun start` via the `--base` flag.

```
# base.ucl

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

## How Jailrun works

Jailrun wires together a set of proven, focused tools — each chosen for a reason.

| Layer               | Tool                                                                                                                         | What it does                                                                           |
|---------------------|------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| OS                  | [FreeBSD](https://www.freebsd.org)                                                                                           | Provides the base system, jail isolation, ZFS, pf, and the userland Jailrun builds on  |
| Virtual machine     | [QEMU](https://www.qemu.org/)                                                                                                | Runs FreeBSD with hardware acceleration (HVF on macOS, KVM on Linux)                   |
| Jail management     | [Bastille](https://bastillebsd.org/)                                                                                         | Creates, destroys, and manages jail lifecycles                                         |
| Provisioning        | [Ansible](https://docs.ansible.com/)                                                                                         | Runs playbooks to install software inside jails and the VM                             |
| Configuration       | [UCL](https://github.com/vstakhov/libucl)                                                                                    | Human-friendly config format, native to FreeBSD                                        |
| Process supervision | [monit](https://mmonit.com/monit/)                                                                                           | Monitors processes inside jails, restarts on failure, runs healthchecks                |
| Filesystem          | [ZFS](https://docs.freebsd.org/en/books/handbook/zfs/) + [9p](https://wiki.qemu.org/Documentation/9p)                        | Instant jail clones via ZFS snapshots; host directory sharing via 9p                   |
| Networking          | [pf](https://docs.freebsd.org/en/books/handbook/firewalls/#firewalls-pf) + [Yggdrasil](https://yggdrasil-network.github.io/) | Packet filter for port forwarding and access control; encrypted mesh between instances |

## Platform support

| Platform            | Status                                |
|---------------------|---------------------------------------|
| macOS Apple Silicon | Tested (HVF acceleration)             |
| macOS Intel         | Should work (HVF), untested           |
| Linux x86_64        | Tested (KVM acceleration)             |
| Linux aarch64       | Should work (KVM), untested           |
| FreeBSD x86_64      | Tested (TCG emulation)                |
| FreeBSD aarch64     | Should work (TCG emulation), untested |

## Roadmap

- [x] **Mesh networking.** Connect Jailrun instances in a private mesh network.
- [x] **Time machine.** Snapshot any jail at any point and roll back instantly using ZFS.
- [ ] **Remote targets.** Deploy jails to remote infrastructure.
- [ ] **Resource limits.** Set per-jail CPU, memory, and I/O constraints.

## Acknowledgments

The isolation, filesystem, and networking features Jailrun exposes are native [FreeBSD](https://www.freebsd.org/) primitives — jails, ZFS, and pf — with decades of engineering behind them.

Thanks to the [FreeBSD Foundation](https://freebsdfoundation.org/) for supporting the continued development of FreeBSD, and to the maintainers of [Bastille](https://bastillebsd.org/), [Ansible](https://docs.ansible.com/), [QEMU](https://www.qemu.org/), and [monit](https://mmonit.com/monit/) for the tools Jailrun builds on.

## License

BSD-3-Clause
