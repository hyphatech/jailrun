# jrun stop

Shut down the VM gracefully.

```bash
jrun stop
```

Sends a shutdown signal to the FreeBSD VM. The VM image and jail state are preserved on disk — `jrun start` will boot from where you left off.
