# jrun up

Create or update jails from a config file.

```bash
jrun up <config>
```

Reads the config, resolves the dependency graph, and deploys each jail in order — create (or clone from a base), mount directories, run provisioning playbooks, wire up ports, and start supervised processes.

## Specific jails { #specific }

Deploy only named jails (dependencies are included automatically):

```bash
jrun up <config> <name...>
```

```bash
jrun up stack.ucl fastapi-314
```

This redeploys `fastapi-314` and any jails it depends on.
