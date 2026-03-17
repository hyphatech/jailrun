# jrun status

Show VM and jail status.

```bash
jrun status
```

```
● VM  running  pid 15604

  uptime     7:10PM  up 15 mins, 0 users, load averages: 1.04, 0.91, 0.85
  disk       9.9G free of 13G
  memory     2.0 GB usable / 4.0 GB total

  name                  state   ip            ports           mounts
  fastapi-314           up      10.17.89.15   tcp/8080→8000   …/examples/fastapi → /srv/app
  hypha-postgres        up      10.17.89.14   tcp/6432→5432   —
  hypha-python-314      up      10.17.89.13   —               —
```

## Tree view { #tree }

Show jails as a dependency tree:

```bash
jrun status --tree
```
