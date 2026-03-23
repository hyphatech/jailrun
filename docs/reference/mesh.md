---
icon: material/lan-connect
---

# Mesh networking

Every jail in Jailrun is more than an isolated sandbox — it is a globally unique network identity. Each jail holds its own cryptographic keypair and is reachable by a stable IPv6 address that belongs to it alone, regardless of where the host machine sits on the Internet.

Jailrun instances can **pair** with each other to form a private encrypted mesh. After pairing, every jail on one machine can reach every jail on the other, and vice versa. There is nothing to configure on a per-jail basis — it just works.

## Why this matters

A few things this makes possible:

- **Collaborate with a teammate** while both of you work locally, then test integrations together in real time. Your jails see each other's jails as if they shared one environment.
- **Connect a local app to a remote database** running in a jail on another host — no tunnels, no port forwarding, no VPN setup.
- **Span a dev environment across machines.** Run your frontend locally and point it at a backend jail on a remote FreeBSD server. DNS names resolve, connections go through, firewalls stay tight.

## How it works

Jailrun builds its mesh on top of [Yggdrasil](https://yggdrasil-network.github.io/), an encrypted IPv6 overlay network. Every participant — the VM and each jail inside it — runs its own Yggdrasil node and gets a `200::/7` address derived from its public key. These addresses are permanent, globally unique, and not tied to any physical network.

```mermaid
flowchart LR
    subgraph hosta["Jailrun A (laptop behind NAT)"]
        JA1[Jail A1] --> VMA[VM A]
        JA2[Jail A2] --> VMA
    end

    subgraph hostb["Jailrun B (remote instance)"]
        VMB[VM B] --> JB1[Jail B1]
        VMB --> JB2[Jail B2]
    end

    VMA -->|encrypted| Relay{{Public relay}}
    Relay -->|encrypted| VMB
```

All traffic on this path is end-to-end encrypted between the two jails. The VMs and the relay route it, but cannot read it.

The VM acts as a **bootstrap node**. It runs Yggdrasil on the jail bridge (`10.17.89.1:19001`) and peers with the public relay:

```mermaid
flowchart TB
    subgraph vm["VM (bootstrap node)"]
        YggHost["Yggdrasil host<br/><code>10.17.89.1:19001</code>"]
    end

    subgraph jails["Jails"]
        J1["jail α<br/>own keypair → own 200::/7 address"]
        J2["jail β<br/>own keypair → own 200::/7 address"]
        J3["jail γ<br/>own keypair → own 200::/7 address"]
    end

    J1 -->|tcp://10.17.89.1:19001| YggHost
    J2 -->|tcp://10.17.89.1:19001| YggHost
    J3 -->|tcp://10.17.89.1:19001| YggHost
    YggHost -->|tcp| Relay{{Public relay}}
```

Each jail peers exclusively with its own VM — it never talks to the relay or the outside world directly.

## The public relay

Both machines need a common point to find each other. This is especially important when one or both are behind NAT, where direct connections are impossible without assistance.

Hypha, the company behind Jailrun, provides a free public Yggdrasil relay — `relay.jail.run` — that any Jailrun instance can use. The relay is just another special Yggdrasil peer with a static IP address and a simple handshake API. It helps nodes discover each other and route traffic, but it cannot decrypt the contents of any session by design.

The relay is configured automatically. You do not need to set anything up or create any accounts.

## Pairing

Pairing is how two Jailrun instances agree to let their jails talk to each other. It is a short handshake coordinated through the relay:

1. **One side creates a pairing** with `jrun pair create`. Jailrun collects the Yggdrasil address of every running jail and sends the roster to the relay, which returns a short code.
2. **The other side joins** with `jrun pair <code>`. It sends its own jail roster to the relay and receives the first side's roster in return.
3. **Both sides update their firewalls and DNS** to allow and resolve the newly paired jails.

After pairing, each side knows the Yggdrasil addresses of the other's jails and opens the firewall for exactly those addresses — nothing more.

List current pairings:

```
jrun pair list
```

```
name      peer       ip                              paired
myapp     a1b2c3     200:abcd:ef01:2345::1           Mar 20 2026, 14:32 UTC
postgres  a1b2c3     200:abcd:ef01:2345::2           Mar 20 2026, 14:32 UTC
```

Remove a pairing anytime:

```
jrun pair remove a1b2c3
```

This drops all firewall allowances and DNS records for that peer's jails.

## Identity

Each jail's Yggdrasil keypair is generated once, on first deploy, and persisted on disk. This means a jail's `200::/7` address is stable across restarts, redeploys, and reboots. Peers that have already paired with it do not need to re-pair — the addresses they whitelisted remain correct.

## Access control

Mesh traffic is **blocked by default**. Every jail runs its own instance of [pf](https://docs.freebsd.org/en/books/handbook/firewalls/#firewalls-pf), and the default ruleset drops all inbound Yggdrasil traffic. Pairing is the only mechanism that opens the firewall, and it does so selectively — only the specific `200::/7` addresses exchanged during the handshake are whitelisted.

In short: if two Jailrun instances are not paired, their jails cannot reach each other over the mesh — even though they may share the same relay. The overlay network provides connectivity and `pf` provides the policy.
