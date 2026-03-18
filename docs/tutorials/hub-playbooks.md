---
icon: material/apps
---

# Hub Playbooks

Jailrun uses [Ansible](https://docs.ansible.com/) for all provisioning. Every jail setup is a playbook you can read, modify, and version. But not every playbook needs to be written from scratch.

## Jailrun Hub

[Jailrun Hub](https://github.com/hyphatech/jailrun-hub) is a curated collection of ready-to-use playbooks for common services — PostgreSQL, Redis, Nginx, Imagor, and more. Point a setup step at a Hub playbook using the `hub://` shorthand:

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

This is equivalent to a full URL:

```
url = "https://github.com/hyphatech/jailrun-hub/blob/main/playbooks/nginx/rolling/playbook.yml";
```

## Pinning versions

Pin to a tag for reproducible builds:

```
url = "hub://nginx/rolling@v1.0.0";
```

```
url = "https://github.com/hyphatech/jailrun-hub/blob/v1.0.0/playbooks/nginx/rolling/playbook.yml";
```

## Passing variables

Pass extra variables into the playbook with `vars` — each Hub playbook documents what it accepts. Works the same way with local playbooks:

```
setup {
  core { type = "ansible"; file = "setup.yml"; vars { APP_ENV = "production"; } }
}
```

## Composing playbooks

Setup isn't limited to a single playbook. You can stack them — mixing Hub playbooks with your own, composing layer by layer:

```
setup {
  nginx {
    type = "ansible";
    url  = "hub://nginx/rolling";
    vars { NGINX_LISTEN_PORT = "80"; }
  }
  app {
    type = "ansible";
    file = "playbooks/deploy-app.yml";
  }
}
```

Playbooks run in the order they're defined.
