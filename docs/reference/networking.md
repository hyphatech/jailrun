---
icon: material/network
---

# Networking

Jailrun boots a VM with its own isolated network. Inside the VM, each jail gets its own network stack — interfaces, routing table, firewall, and the ability to bind any port without conflict. Jails discover each other by name, and port forwarding makes their services reachable from your host.

## Bridge and subnet

All jails use **VNET** and are bridged together on `bridge0` inside the VM. Each jail receives a dedicated virtual network interface attached to the bridge.

The jail subnet is `10.17.89.0/24`. The bridge sits at `10.17.89.1`, and jails are assigned addresses from `10.17.89.10` to `10.17.89.250`.

## IP assignment

You can also assign a static IP in your jail config:

```
jail "myapp" {
  ip = "10.17.89.50";
}
```

If you omit `ip`, Jailrun assigns one automatically during `jrun up`. It probes the subnet to find unused addresses and assigns the first available IP to each jail that needs one. Once assigned, a jail keeps its IP across further redeploys.

## DNS

Jailrun runs [`local_unbound`](https://man.freebsd.org/cgi/man.cgi?query=local-unbound) inside the VM so that jails can discover each other by name. Every jail gets a DNS record under the `local.jrun` domain:

```
<jail-name>.local.jrun → <jail-ip>
```

For example, a jail called `postgres` with IP `10.17.89.42` is reachable at `postgres.local.jrun` from all jails. You can use this hostname directly in database connection strings, HTTP requests, config files — anywhere a hostname is accepted.

```
# From inside any jail
fetch http://myapp.local.jrun:8080/health
psql -h postgres.local.jrun -U postgres
```

The VM's resolver is configured with `search local.jrun`, so short names like `postgres` also work without the full suffix. Queries for names outside the `jrun` zone are forwarded upstream, so jails retain full internet access.

DNS records are updated automatically on every `jrun up` and `jrun down`.

## Firewall

[pf](https://docs.freebsd.org/en/books/handbook/firewalls/#firewalls-pf) is FreeBSD's built-in packet filter — it handles firewalling, NAT, and traffic redirection. Jailrun uses it at two levels: the VM and each individual jail. The default policy blocks all unsolicited inbound traffic.

The VM's pf handles NAT for outbound jail traffic and port-forwarding rules generated from `forward` blocks. Each jail also runs its own pf instance, configured and started automatically during deploy.

## Port forwarding

Port forwarding lets you reach a jail's services from your host machine. In the config:

```
jail "myapp" {
  forward {
    http { host = 8080; jail = 8080; }
  }
}
```

This creates a QEMU port forward from `localhost:8080` on your host to the jail's IP at port `8080` inside the VM. If the forwarding configuration changes between deploys, Jailrun automatically restarts the VM to apply the new wiring — QEMU port maps are set at launch time.
