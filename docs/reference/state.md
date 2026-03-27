---
icon: material/state-machine
---

# State reference

Jailrun is declarative — you describe what you want, and `jrun` figures out how to get there. Under the hood, this works through two concepts: **state** and **plan**.

## State

State is a JSON file at `~/.jrun/state.json` that records the current reality — what's running, what's mounted, what's forwarded. Jailrun reads it on every `jrun up` to understand what already exists before making changes.

The state tracks:

- **Base configuration** — VM-level setup, port forwards, and mounts
- **Jails** — each jail's name, release, IP, base, forwards, mounts, and supervised processes
- **QEMU wiring** — the port forwards and shared directories currently passed to the VM process
- **SSH port** — the port used to reach the VM

??? example "Example state.json"

    ```json
    {
      "version": 1,
      "base": {
        "setup": {},
        "forwards": {},
        "mounts": {}
      },
      "jails": {
        "python-314": {
          "name": "python-314",
          "base": null,
          "release": "15.0-RELEASE",
          "ip": "10.17.89.10",
          "forwards": {},
          "mounts": {},
          "execs": {},
          "setup": {
            "python": {
              "type": "ansible",
              "file": "playbooks/python-314.yml",
              "vars": {}
            }
          }
        },
        "postgres-16": {
          "name": "postgres-16",
          "base": null,
          "release": "15.0-RELEASE",
          "ip": "10.17.89.11",
          "forwards": {
            "pg": {
              "proto": "tcp",
              "host": 6432,
              "jail": 5432
            }
          },
          "mounts": {},
          "execs": {},
          "setup": {
            "postgres": {
              "type": "ansible",
              "url": "hub://postgres/16",
              "vars": {}
            }
          }
        },
        "fastapi-314": {
          "name": "fastapi-314",
          "base": {
            "type": "jail",
            "name": "python-314"
          },
          "release": "15.0-RELEASE",
          "ip": "10.17.89.12",
          "forwards": {
            "http": {
              "proto": "tcp",
              "host": 8080,
              "jail": 8000
            }
          },
          "mounts": {
            "src": {
              "host": "/Users/you/Projects/fastapi",
              "jail": "/srv/app"
            }
          },
          "execs": {
            "uvicorn": {
              "cmd": "python3.14 -m uvicorn app:app --reload --host 0.0.0.0",
              "dir": "/srv/app",
              "env": {},
              "healthcheck": {
                "test": "fetch -qo /dev/null http://127.0.0.1:8000",
                "interval": "30s",
                "timeout": "10s",
                "retries": 5
              }
            }
          },
          "setup": {
            "fastapi": {
              "type": "ansible",
              "file": "playbooks/fastapi-314.yml",
              "vars": {}
            }
          }
        }
      },
      "launched_fwds": [
        { "proto": "tcp", "host": 6432, "guest": 6432 },
        { "proto": "tcp", "host": 8080, "guest": 8080 }
      ],
      "launched_shares": [
        {
          "host": "/Users/you/Projects/fastapi",
          "id": "fs_3c197bfb31",
          "mount_tag": "jrun_3c197bfb31"
        }
      ],
      "ssh_port": 2222
    }
    ```

## Plan

Before making any changes, jrun compares the desired config against the current state and produces a plan — the precise set of actions needed to bring reality in line with the config.

The plan includes:

- **Jails to create** — new jails or jails cloned from a base
- **Mounts to set up** — host directories shared into the VM and nullfs mounts into jails
- **Processes to start** — supervised commands with optional healthchecks
- **Port forwards to wire** — host-to-jail port mappings via pf
- **Stale jails to remove** — jails that exist in state but are no longer in the config
- **Stale mounts to clean up** — mounts that are no longer needed

If the port forwarding or mount configuration changed in a way that affects QEMU's startup arguments, jrun detects this and restarts the VM automatically before applying the rest of the plan.

## How they work together

``` mermaid
graph LR
  UCL["stack.ucl\n(desired)"] --> DIFF["Compare"]
  STATE["state.json\n(current)"] --> DIFF
  DIFF --> PLAN["Plan"]
  PLAN --> EXEC["Execute"]
  EXEC --> UPDATED["state.json\n(updated)"]
```

This is what makes jrun idempotent — running `jrun up` twice with the same config produces no changes the second time. And it's what makes partial deploys safe.
