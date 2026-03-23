# jrun pair

Manage [mesh pairings](mesh.md) with other Jailrun instances — create, join, list, and drop.

## Create a pairing

```bash
jrun pair
```

Collects the Yggdrasil address of every running jail, sends the roster to the relay, and returns a short code. Share this code with your peer.

```
Code:  81-zephyr-night-climb
Tell your peer:  jrun pair 81-zephyr-night-climb
```

Jailrun then polls the relay until the other side joins.

## Join a pairing { #join }

```bash
jrun pair <code>
```

```bash
jrun pair 81-zephyr-night-climb
```

Sends your jail roster to the relay and receives the peer's roster in return. Both sides update their firewalls and DNS immediately — jails can reach each other as soon as the command completes.

## List pairings { #list }

```bash
jrun pair --list
```

```
name      peer                    ip                       paired
myapp     81-zephyr-night-climb   200:abcd:ef01:2345::1    Mar 20 2026, 14:32 UTC
postgres  81-zephyr-night-climb   200:abcd:ef01:2345::2    Mar 20 2026, 14:32 UTC
```

Each row is a remote jail. You can reach it by the displayed IPv6 address or by its fully qualified name — `<jail-name>.<pair-code>.jrun`. In this example, the remote `postgres` jail is reachable at `postgres.81-zephyr-night-climb.jrun`.

## Drop a pairing { #drop }

```bash
jrun pair --drop <code>
```

```bash
jrun pair --drop 81-zephyr-night-climb
```

Drops all firewall allowances and DNS records for that peer's jails. The remote side is not notified and their traffic will simply be blocked by your firewall.
