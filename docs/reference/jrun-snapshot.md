# jrun snapshot

Manage ZFS snapshots for jails — create, list, rollback, and delete.

## Create a snapshot

```bash
jrun snapshot create <jail>
```

Creates a snapshot with an auto-generated UTC timestamp name like `2026-03-19_00-38-14`.

```bash
jrun snapshot create hypha-redis
```

### Named snapshot { #named }

```bash
jrun snapshot create <jail> <name>
```

```bash
jrun snapshot create hypha-redis before-upgrade
```

Snapshots are instant and taken while the jail is running — no downtime required. They capture the full jail filesystem at that exact point in time.

## List snapshots { #list }

```bash
jrun snapshot list <jail>
```

```bash
jrun snapshot list hypha-redis
```

```
name                  used   created
before-upgrade        0B     Wed Mar 19 00:38 2026
2026-03-19_01-15-42   88K    Wed Mar 19 01:15 2026
```

The `used` column shows how much data has changed since the snapshot was taken. A snapshot with `0B` used means nothing has changed.

## Rollback to a snapshot { #rollback }

```bash
jrun snapshot rollback <jail> <name>
```

```bash
jrun snapshot rollback hypha-redis before-upgrade
```

Stops the jail, reverts the filesystem to the snapshot, and starts the jail again. Any snapshots newer than the target are destroyed — ZFS does not support rolling back to an older snapshot while keeping newer ones.

Requires confirmation before proceeding.

## Delete a snapshot { #delete }

```bash
jrun snapshot delete <jail> <name>
```

```bash
jrun snapshot delete hypha-redis before-upgrade
```

Requires confirmation before proceeding. Fails with a clear message if the snapshot does not exist.
