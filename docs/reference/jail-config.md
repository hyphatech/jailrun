# Jail config

A jail config file defines one or more jails using [UCL](https://github.com/vstakhov/libucl) — a clean, human-friendly format native to FreeBSD.

## Full example

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

## Blocks

### `release`

FreeBSD release to use for the jail. Defaults to the VM's version if omitted.

```
release = "15.0-RELEASE";
```

### `ip`

Static IP address for the jail. Auto-assigned if omitted.

```
ip = "10.17.89.50";
```

### `base`

Clone the jail from an existing one instead of creating from scratch. The clone is a ZFS snapshot — instant, and uses no extra disk space until it diverges.

```
base { type = "jail"; name = "base-jail"; }
```

### `depends`

Other jails that must be deployed before this one. jrun resolves the full dependency graph automatically.

```
depends ["postgres", "redis"]
```

### `mount`

Share directories from your host into the jail. Changes sync instantly in both directions.

```
mount {
  src { host = "."; jail = "/srv/app"; }
  data { host = "./data"; jail = "/var/data"; }
}
```

### `forward`

Forward ports from your host to the jail.

```
forward {
  http { host = 8080; jail = 8080; }
  debug { host = 9229; jail = 9229; }
}
```

### `exec`

Supervised processes inside the jail. Monitored and auto-restarted on failure.

```
exec {
  server {
    cmd = "gunicorn app:main -b 0.0.0.0:8080";
    dir = "/srv/app";
  }
}
```

#### `env`

Environment variables for the process.

```
env {
  DATABASE_URL = "postgresql://hypha-postgres/mydb";
  APP_ENV = "production";
}
```

#### `healthcheck`

The process supervisor runs the test command at the given interval. If it fails after the configured retries, the process is restarted.

```
healthcheck {
  test = "fetch -qo /dev/null http://127.0.0.1:8080/health";
  interval = "30s";
  timeout = "10s";
  retries = 5;
}
```

### `setup`

[Ansible](https://docs.ansible.com/) playbooks for provisioning, run in order when the jail is first created. You can mix local playbooks with [Jailrun Hub](https://github.com/hyphatech/jailrun-hub) playbooks.

Local playbook:

```
setup {
  core { type = "ansible"; file = "install-deps.yml"; }
}
```

Hub playbook:

```
setup {
  nginx {
    type = "ansible";
    url  = "hub://nginx/rolling";
    vars { NGINX_LISTEN_PORT = "80"; }
  }
}
```

Pass extra variables into the playbook with `vars`. Each Hub playbook documents what it accepts.
