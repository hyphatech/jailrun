# jrun status

Show VM and jail status.

## Overview

```bash
jrun status
```

![jrun status](../assets/status/jrun-status.png)

## Extra columns

Use `--show` / `-s` to add columns to the overview table.

```bash
jrun status --show ip
jrun status --show services
jrun status --show ip --show services
jrun status --show all                  # shorthand for ip + services
```

![jrun status show ip](../assets/status/jrun-status-show-ip.png)

## Tree view

```bash
jrun status --tree
```

![jrun status tree](../assets/status/jrun-status-tree.png)

Tree view also respects `--show`:

```bash
jrun status --tree --show all
```

![jrun status tree show all](../assets/status/jrun-status-tree-show-all.png)

This adds `ip` rows and `service` rows to each jail node.

## Jail detail

Pass a jail name to see its full detail view:

```bash
jrun status fastapi-314
```

![jrun status jail](../assets/status/jrun-status-jail.png)


The detail view shows monit service metrics (cpu, mem, uptime) when available.

### Detail tree view

```bash
jrun status fastapi-314 --tree
```

![jrun status jail tree](../assets/status/jrun-status-jail-tree.png)

## Live monitor

Watch service metrics in real time with CPU and memory sparklines:

```bash
jrun status fastapi-314 --live
```

![jrun status jail live](../assets/status/jrun-status-jail-live.png)

The display refreshes every 5 seconds. Sparklines show the last 20 samples.

### Live tree view

```bash
jrun status fastapi-314 --live --tree
```

Same data rendered as a tree instead of a table, with sparklines inline next to each metric.

![jrun status jail live tree](../assets/status/jrun-status-jail-live-tree.png)

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--tree` | `-t` | Render as tree instead of table |
| `--show` | `-s` | Extra columns: `ip`, `services`, `all` |
| `--live` | `-l` | Live service monitor with sparklines (requires jail name) |
