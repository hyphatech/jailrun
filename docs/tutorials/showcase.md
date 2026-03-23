---
icon: material/star-outline
---

# Showcase

A few ways to explore what jrun can do beyond the basics.

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
jail "hugoplate" {
  setup {
    hugo {
      type = "ansible";
      url  = "hub://hugoplate/0.157";
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

A few minutes later — a full XFCE desktop running inside FreeBSD. A [KDE Plasma](https://github.com/hyphatech/jailrun-hub/tree/main/playbooks/kde/rolling) variant is also available in Jailrun Hub.
