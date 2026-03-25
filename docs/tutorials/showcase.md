---
icon: material/star-outline
---

# Showcase

A few fun ways to explore what Jailrun can do beyond the basics.

## Jailed Matrix Server

Jailrun's built-in [mesh network](../reference/mesh) support makes it easy to self-host a [Matrix](https://matrix.org/) server
directly on your laptop, letting you set up genuinely encrypted direct messaging with anyone worldwide — no boundaries, no middlemen.

Decide who will run the Matrix server in Jailrun and bring it up:

```
jail "matrix-server" {
  setup {
    continuwuity {
      type = "ansible";
      file  = "examples/labs/matrix.yml";
      vars {
        CONTINUWUITY_SERVER_NAME    = "matrix.local";
        CONTINUWUITY_ADMIN_USER     = "admin";
        CONTINUWUITY_ADMIN_PASSWORD = "admin";
      }
    }
  }
  forward {
    client { host = 6167; jail = 6167; }
  }
  exec {
    build {
      cmd = "/usr/local/bin/conduwuit --config /usr/local/etc/continuwuity/conduwuit.toml";
    }
  }
}
```

```bash
jrun up matrix-server.ucl
```

The server name can be anything you like — no real domain required.

Meanwhile, the other peer prepares a proxy jail for pairing:

```
jail "matrix-proxy" {
  setup {
    tcp_proxy {
      type = "ansible";
      url  = "hub://haproxy/rolling";
    }
  }
}
```

```bash
jrun up matrix-proxy.ucl
```

Once both jails are provisioned, create a new mesh session on the server side:

```
jrun pair

Code:  18-pulse-lilac
Tell your peer:  jrun pair 18-pulse-lilac
```

Share the code with your peer through any convenient channel. On their side:

```
jrun pair 18-pulse-lilac
```

After the pairing is established, they can list paired jails to get the connection details needed for the config update:

```
jrun pair --list

  name            peer             ip                                       paired
  matrix-server   18-pulse-lilac   200:557d:60a2:4549:188e:c376:ce00:4a6b   Mar 24 2026, 23:06 UTC
```

Then define port forwarding from the remote jail to the local one, and from the local jail to the host, so the Matrix client on the host can reach it:

```
jail "matrix-proxy" {
  setup {
    tcp_proxy {
      type = "ansible";
      url  = "hub://haproxy/rolling";
      vars {
        HAPROXY_TCP_MAPPINGS = "
          6167 matrix-server.18-pulse-lilac.jrun 6167
        ";
      }
    }
  }
  forward {
    client { host = 6167; jail = 6167; }
  }
}
```

Congrats! Both of you can now connect to your own Matrix server at `http://localhost:6167` using Element, Fractal, or any other compatible client for secure messaging.

## Jailed AstroNvim

Run a full [AstroNvim](https://astronvim.com/) setup without installing anything on your host.

```
jail "astronvim" {
  setup {
    astronvim { type = "ansible"; url = "hub://astronvim/rolling"; }
  }
  mount {
    src { host = "."; jail = "/srv/project"; }
  }
}
```

```bash
jrun up nvim.ucl
jrun cmd astronvim nvim
```

Alias it in `~/.zshrc` and use it as if it were installed locally:

```bash
alias nvim="jrun cmd astronvim nvim"
```

You can stack playbooks too — here's an OCaml environment with AstroNvim and a custom config, all composed layer by layer:

```
jail "fp-astronvim" {
  setup {
    ocaml     { type = "ansible"; url  = "hub://ocaml/rolling"; }
    astronvim { type = "ansible"; url  = "hub://astronvim/rolling"; }
    custom    { type = "ansible"; file = "local/playbook.yml"; }
  }
  mount {
    src { host = "."; jail = "/srv/project"; }
  }
}
```

## Jailed Hugo

A complete [Hugo](https://gohugo.io/) environment inside a jail with live file watching. You edit on your host, Hugo rebuilds inside the jail.

Create an empty project directory, then define the jail:

```
jail "hugo" {
  setup {
    hugo {
      type = "ansible";
      url  = "hub://hugo/0.157";
      vars { HUGO_SITE_DIR = "/srv/project"; }
    }
  }
  mount {
    src { host = "~/Projects/hugo"; jail = "/srv/project"; }
  }
  forward {
    http { host = 1313; jail = 1313; }
  }
  exec {
    build {
      cmd = "hugo server --source /srv/project --bind 0.0.0.0 --port 1313 --poll 1s";
    }
  }
}
```

```bash
jrun up hugo.ucl
```

Open `http://localhost:1313` — edit files on your host, Hugo picks up changes instantly.

## Jailed I2P

Run your own [I2P](https://geti2p.net) proxy using [i2pd](https://i2pd.website/), a lightweight C++ implementation of the I2P router:

```
jail "hypha-i2pd" {
  setup {
    i2pd {
      type = "ansible";
      url  = "hub://i2pd/rolling";
    }
  }
  forward {
    i2pd-http-proxy { host = 4444; jail = 4444; }
    i2pd-socks      { host = 4447; jail = 4447; }
    i2pd-console    { host = 7070; jail = 7070; }
  }
}
```

Configure your browser to use manual proxy settings — HTTP proxy `localhost` on port `4444`, with "Also use this proxy for HTTPS" checked. The web console is available at `http://127.0.0.1:7070`.

This routes all browser traffic through i2pd and only `.i2p` addresses will resolve.

!!! tip
    Use a dedicated browser profile to keep regular browsing unaffected.

## Boot into XFCE

Jailrun isn't limited to headless services. Provision a full FreeBSD desktop and launch the VM with a graphical window.

Stop the VM if it's running, then create a `base.ucl`:

```
base {
  setup {
    desktop { type = "ansible"; url = "hub://xfce/rolling"; }
  }
}
```

```bash
jrun start --base base.ucl --mode graphic
```

A few minutes later — a full XFCE desktop running inside FreeBSD. A [KDE Plasma](https://github.com/hyphatech/jailrun-hub/tree/main/playbooks/kde/rolling) variant is also available in [Jailrun Hub](https://hub.jail.run).
