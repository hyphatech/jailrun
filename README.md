# Jailrun

Jailrun is a cross-platform orchestration tool for FreeBSD jails. Its CLI, `jrun`, brings FreeBSD to your host system and manages jails inside it — each with its own filesystem, network, and processes. Define your stack in a config file and `jrun` handles the rest.

<p align="center">
  <img src="https://raw.githubusercontent.com/hyphatech/jailrun/main/screenshot.png" alt="screenshot" width="100%" />
</p>

## What is a jail?

A jail is a self-contained environment running inside FreeBSD. Nothing inside a jail can see or touch anything outside of it — and nothing outside can interfere with what's inside.

Jails are a native FreeBSD feature. They're fast to create, cheap to run, and easy to destroy and recreate from scratch. FreeBSD jails are one of the most proven isolation technologies in computing — and jrun makes them accessible from macOS, Linux, and FreeBSD itself.

## ZFS

Jailrun uses [ZFS](https://docs.freebsd.org/en/books/handbook/zfs/) as the backing filesystem for all jails, making snapshots instant and free on disk.

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

Install Python 3.13+ using your operating system’s package manager or preferred installation method.

Install uv using your distribution’s package manager if available, or via the official installer:

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
sudo pkg install qemu edk2-qemu-x64 uv rust cdrtools python313
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

If jrun is not found after installation, make sure uv’s user bin directory is on your PATH:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Quick start

Bring FreeBSD to your system:

```bash
jrun start
```

On first run, jrun downloads a FreeBSD image, boots the VM with hardware acceleration (HVF on macOS, KVM on Linux), and sets up SSH for further provisioning.

After provisioning, connect:

```bash
jrun ssh
```

Prefer an interactive experience? Run `jrun` with no arguments to enter the shell — guided wizards, autocomplete, and command history all included.

```bash
jrun
```

## Your first jail

Jails are defined in config files using [UCL](https://github.com/vstakhov/libucl) — a clean, human-friendly format similar to JSON.

Create a file called `web.ucl` in your project directory:

```
jail "simple-server" {
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

One config file, one command and you can safely interact with your app from the host.

## A real-world stack

Here's something more realistic: a FastAPI application running on Python 3.14, backed by PostgreSQL. Three jails, each doing one thing, all wired together.

```
# stack.ucl

jail "hypha-python-314" {
  setup {
    python { type = "ansible"; file = "playbooks/python-314.yml"; }
  }
}

jail "hypha-postgres" {
  setup {
    postgres { type = "ansible"; file = "playbooks/postgres.yml"; }
  }
  forward {
    pg { host = 6432; jail = 5432; }
  }
}

jail "fastapi-314" {
  base { type = "jail"; name = "hypha-python-314"; }

  depends ["hypha-postgres"]

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
    httpserver {
      cmd = "python3.14 -m uvicorn app:app --reload";
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

- **Each `setup` block points to an Ansible playbook** that runs when the jail is first created. `hypha-python-314` compiles Python 3.14 from source. `hypha-postgres` installs and configures PostgreSQL.

- **Block `base` clones one jail from another.** Compiling from source might be slow. You do it once in `hypha-python-314`, then `fastapi-314` is created as a ZFS clone — a fully independent copy ready in milliseconds, using no extra disk space until it diverges from the base.

- **Block `depends` controls deploy order.** jrun resolves the dependency graph automatically. In this case: `hypha-python-314` first (it's the base), then `hypha-postgres` (it's a dependency), then `fastapi-314` last.

- **Jails discover each other by name.** From inside `fastapi-314`, you can `ping hypha-postgres.jrun` — it just works. Use jail names directly in your app's database config.

- **Port forwarding works from your host.** PostgreSQL is reachable at `localhost:6432`. Your FastAPI app is at `localhost:8080`. Healthchecks are built in — the process supervisor monitors it and restarts it if the check fails.

- **Live reload works out of the box.** Your project directory is shared into the jail. Uvicorn's `--reload` sees file changes instantly.

Check on everything:

```bash
$ jrun status

  ● VM  running  pid 15604

  uptime     7:10PM  up 15 mins, 0 users, load averages: 1.04, 0.91, 0.85
  disk       9.9G free of 13G
  memory     2.0 GB usable / 4.0 GB total

  name                  state   ip            ports           mounts
  fastapi-314           up      10.17.89.15   tcp/8080→8000   …/examples/fastapi → /srv/app
  hypha-postgres        up      10.17.89.14   tcp/6432→5432   —
  hypha-python-314      up      10.17.89.13   —               —
```

Drop into any jail to debug or inspect:

```bash
jrun ssh hypha-postgres
```

Run a command inside a jail without opening a shell:

```bash
jrun cmd hypha-postgres psql -U postgres -c 'SELECT version()'
```

## Using shared playbooks

Not every playbook needs to be written from scratch. [Jailrun Hub](https://github.com/hyphatech/jailrun-hub) is a curated collection of ready-to-use playbooks for common services — Redis, Nginx, PostgreSQL, and more.

Point a setup step at a Hub playbook with `url` instead of `file`:

```
jail "hypha-nginx" {
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
jail "hypha-nginx" {
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

`vars` passes variables into the playbook — each playbook documents what it accepts. Works the same way with local playbooks:

```
setup {
  core { type = "ansible"; file = "setup.yml"; vars { APP_ENV = "production"; } }
}
```

## Running a graphical desktop

Jailrun isn't limited to headless services. You can provision a full FreeBSD desktop and launch the VM with a QEMU graphical window — useful for running GUI applications in a clean, isolated environment.

Create a `base.ucl` at the VM level:

```
# base.ucl

base {
  setup {
    desktop {
      type = "ansible";
      url  = "hub://xfce/rolling";
      vars { X_RESOLUTION = "1920x1080"; }
    }
  }
}
```

Apply the base config and boot with a graphical display:

```bash
jrun start --base base.ucl --mode graphic
```

QEMU opens a window with an XFCE desktop running inside FreeBSD — full mouse and keyboard support, with hardware acceleration. A [KDE Plasma](https://github.com/hyphatech/jailrun-hub/tree/main/playbooks/kde/rolling) variant is also available in Jailrun Hub.

## Updating and tearing down

To redeploy a single jail after changing its config:

```bash
jrun up stack.ucl fastapi-314
```

To stop jails without destroying them:

```bash
jrun pause stack.ucl
```

This stops the jail and its supervised processes but leaves the state, mounts, and port forwards intact. To stop specific jails:

```bash
jrun pause stack.ucl hypha-postgres
```

To tear down specific jails:

```bash
jrun down stack.ucl hypha-python-314
```

Other jails are left untouched. To tear down everything defined in a config:

```bash
jrun down stack.ucl
```

## Testing with jails

Jails integrate naturally with test suites. Here's an example of a pytest fixture that brings up a PostgreSQL jail before your tests and cleans it up afterward:

```python
from collections.abc import Generator

import psycopg
import pytest

from jailrun import ROOT_DIR
from jailrun.settings import Settings
from jailrun.testing.postgres import PostgresJail


@pytest.fixture
def postgres_jail() -> Generator[PostgresJail]:
    with PostgresJail("hypha-postgres-test", jail_config=ROOT_DIR / "tests" / "postgres.ucl") as jail:
        yield jail


@pytest.fixture
def postgres_conn(settings: Settings, postgres_jail: PostgresJail) -> Generator[psycopg.Connection]:
    with psycopg.connect(
        host=settings.vm_host, port=postgres_jail.port, dbname=postgres_jail.dbname, user=postgres_jail.user
    ) as conn:
        yield conn


def test_insert_and_query(postgres_conn: psycopg.Connection) -> None:
    with postgres_conn.cursor() as cur:
        cur.execute("CREATE TABLE users (id serial, name text)")
        cur.execute("INSERT INTO users (name) VALUES ('alice')")
        row = cur.execute("SELECT name FROM users WHERE name = 'alice'").fetchone()
        assert row

        [value] = row
        assert value == "alice"


def test_empty_after_cleanup(postgres_conn: psycopg.Connection) -> None:
    with postgres_conn.cursor() as cur:
        tables = cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
        assert tables == []
```

Your tests run against a real PostgreSQL in its own jail, not an in-memory substitute. Jailrun includes ready-to-use testing fixtures for PostgreSQL, Redis, InfluxDB, MariaDB, and MySQL.

## Commands

| Command                               | Description |
|---------------------------------------|-------------|
| `jrun`                                | Interactive shell |
| `jrun start`                          | Boot the VM (downloads FreeBSD on first run) |
| `jrun start --base <config>`          | Boot the VM with a base config applied |
| `jrun start --provision`              | Re-run base provisioning on an already-booted VM |
| `jrun start --mode graphic`           | Boot the VM with a graphical QEMU display |
| `jrun stop`                           | Shut down the VM gracefully |
| `jrun ssh`                            | SSH into the VM |
| `jrun ssh <name>`                     | SSH directly into a jail |
| `jrun cmd <name> <executable> [args]` | Run a command inside a jail |
| `jrun up <config>`                    | Create or update all jails in a config |
| `jrun up <config> <name...>`          | Deploy specific jails (dependencies included automatically) |
| `jrun pause`                          | Interactively select existing jails to stop without destroying them |
| `jrun pause <name...>`                | Stop specific existing jails without destroying them |
| `jrun down`                           | Interactively select existing jails to destroy |
| `jrun down <name...>`                 | Destroy specific jails |
| `jrun status`                         | Show VM and jail status |
| `jrun status --tree`                  | Show VM and jail status as a tree |
| `jrun purge`                          | Stop and destroy the VM with all jails |

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
        DATABASE_URL = "postgresql://hypha-postgres/mydb";
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

Optional VM-level config for customizing the base system. Passed to `jrun start` and `jrun up` via the `--base` flag.

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

## Environment variables

All settings have sensible defaults. Override them with environment variables if you need to.

| Variable | Default | Description |
|----------|---------|-------------|
| `JRUN_SSH_PORT` | `2222` | Host port for VM SSH |
| `JRUN_BSD_VERSION` | `15.0` | FreeBSD version |
| `JRUN_BSD_ARCH` | auto-detected | Architecture (`aarch64` or `amd64`) |
| `JRUN_QEMU_MEMORY` | `4096M` | VM memory |
| `JRUN_QEMU_DISK_SIZE` | `20G` | VM disk size |

## How Jailrun works

Jailrun wires together a set of proven, focused tools — each chosen for a reason.

| Layer | Tool | What it does |
|-------|------|--------------|
| Virtual machine | [QEMU](https://www.qemu.org/) | Runs FreeBSD with hardware acceleration (HVF on macOS, KVM on Linux) |
| Jail management | [Bastille](https://bastillebsd.org/) | Creates, destroys, and manages jail lifecycles |
| Provisioning | [Ansible](https://docs.ansible.com/) | Runs playbooks to install software inside jails and the VM |
| Configuration | [UCL](https://github.com/vstakhov/libucl) | Human-friendly config format, native to FreeBSD |
| Process supervision | [monit](https://mmonit.com/monit/) | Monitors processes inside jails, restarts on failure, runs healthchecks |
| Filesystem | [ZFS](https://docs.freebsd.org/en/books/handbook/zfs/) + [9p](https://wiki.qemu.org/Documentation/9p) | Instant jail clones via ZFS snapshots; host directory sharing via 9p |
| Networking | [pf](https://docs.freebsd.org/en/books/handbook/firewalls/#firewalls-pf) | FreeBSD's packet filter handles port forwarding between host and jails |

The lifecycle is controlled by three base commands:

- `jrun start` provisions FreeBSD on your host in QEMU.
- `jrun up` reads your config, resolves the dependency graph, and deploys each jail in order:
  - create (or clone from a base)
  - mount shared directories
  - run provisioning playbooks
  - register jail name as a reachable host for other jails
  - wire up port forwards
  - start supervised processes
- `jrun down` removes a jail and cleans up its mounts, ports, and processes without affecting the rest.

## Platform support

| Platform | Status |
|----------|--------|
| macOS Apple Silicon | Tested (HVF acceleration) |
| macOS Intel | Should work (HVF), untested |
| Linux x86_64 | Tested (KVM acceleration) |
| Linux aarch64 | Should work (KVM), untested |
| FreeBSD x86_64 | Tested (TCG emulation) |
| FreeBSD aarch64 | Should work (TCG emulation), untested |

## Roadmap

- [ ] **Resource limits.** Set per-jail CPU, memory, and I/O constraints.
- [ ] **Time machine.** Snapshot any jail at any point and roll back instantly using ZFS.
- [ ] **Modular UCL.** Compose configs from reusable, shareable modules.
- [ ] **Remote targets.** Deploy jails to remote infrastructure. Local and remote in one mesh, same config format.

## Acknowledgments

The isolation, filesystem, and networking features Jailrun exposes are native [FreeBSD](https://www.freebsd.org/) primitives — jails, ZFS, and pf — with decades of engineering behind them.

Thanks to the [FreeBSD Foundation](https://freebsdfoundation.org/) for supporting the continued development of FreeBSD, and to the maintainers of [Bastille](https://bastillebsd.org/), [Ansible](https://docs.ansible.com/), [QEMU](https://www.qemu.org/), and [monit](https://mmonit.com/monit/) for the tools Jailrun builds on.

## License

BSD-3-Clause
