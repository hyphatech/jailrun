# jrun down

Destroy jails and clean up their mounts, ports, and processes.

```bash
jrun down
```

Interactively select which jails to destroy.

## Specific jails { #specific }

Destroy named jails directly:

```bash
jrun down <name...>
```

```bash
jrun down hypha-python-314
```

Other jails are left untouched.
