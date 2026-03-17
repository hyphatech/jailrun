# jrun pause

Stop jails without destroying them.

```bash
jrun pause
```

Interactively select which running jails to stop. The jail's state, mounts, and port forwards are left intact.

## Specific jails { #specific }

Stop named jails directly:

```bash
jrun pause <name...>
```

```bash
jrun pause hypha-postgres
```
