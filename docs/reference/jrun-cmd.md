# jrun cmd

Run a command inside a jail without opening a shell.

```bash
jrun cmd <n> <executable> [args]
```

## Example

```bash
jrun cmd postgres-16 psql -U postgres -c 'SELECT version()'
```

The command runs inside the jail and its output is printed to your terminal. Useful for one-off tasks, health checks, and scripting.
