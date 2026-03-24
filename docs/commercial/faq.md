---
icon: material/help-circle-outline
---

# Frequently asked questions

---

## :material-cloud-off-outline: Why not just stay on AWS / GCP / Azure?

For some businesses it makes sense — genuinely unpredictable traffic spikes,
large teams already fluent on the platform, compliance tied to specific managed
services or zones. If that's you, stay.

For most startups and small-to-medium companies it isn't. You're paying for
elasticity you don't use, managed services that solved a problem you no longer
have, and a billing model where the ceiling is invisible until the invoice
arrives.

---

## :material-server-network: What is bare metal?

A bare metal server is a physical machine dedicated entirely to you. No
hypervisor, no shared resources, no noisy neighbours. You get all the CPU,
RAM, and storage — exactly as specified, consistently.

A VPS or cloud instance is a virtual machine running on top of shared physical
hardware. It's cheaper and more flexible, but the performance is variable,
the resources are shared, and the pricing model is designed to scale with
your usage in ways that are difficult to predict.

Bare metal servers are billed at a fixed monthly rate regardless of your
traffic, CPU usage, or storage consumption. That predictability is a large
part of why the economics work.

They are also commonly called dedicated servers — the terms are interchangeable.

**Providers I work with:**

- [OVHcloud](https://ovhcloud.com) — European, strong value, unmetered traffic included
- [Hetzner](https://hetzner.com) — German, excellent price-performance, very popular with European teams

The right choice depends on your location requirements, budget, and workload.
The audit includes a specific recommendation with reasoning.

---

## :material-lightning-bolt-outline: Why FreeBSD and not Linux?

FreeBSD ships as a complete, coherent OS — kernel, userland, base tools, and
libraries all developed together, versioned together, and tested together as a
single unit. That coherence matters. It's part of why FreeBSD solutions tend
to be cleaner and why the base system behaves consistently across installations.

FreeBSD jails have been a mature isolation primitive since 2000 — simpler to
reason about than containers, lower overhead, and with native ZFS integration
that makes data integrity and backups solid at the filesystem level rather than
bolted on top.

ZFS is a significant part of this story. Instant snapshots, copy-on-write,
checksummed storage — backups that are trivial to run and nearly instant to
restore. It's the kind of reliability that's difficult and expensive to
replicate on managed cloud storage.

This is the stack we run in production for [hypha.tv](https://hypha.tv), and
the one Jailrun was built to manage.

---

## :material-transit-transfer: What does unmetered traffic actually mean?

Most bare metal providers in Europe include unlimited ingress and egress
traffic at no extra cost. AWS, GCP, and Azure charge per gigabyte out — and
it adds up fast.

For [hypha.tv](https://hypha.tv) — a video platform with heavy egress — this
difference alone saves tens of thousands per year. For any business with
meaningful outbound traffic (video, file storage, data exports, APIs with
large responses, frequent backups) this is often the single biggest line item
in the savings case.

---

## :material-account-outline: Is this just one person?

Yes, and that's the point.

You get direct access to the engineer who designed and built your system. When
something needs attention, the person who responds is the same person who knows
why every decision was made. No tickets, no handoffs, no junior on-call who
has to escalate before anything happens.

For clients who need formal SLA guarantees or contractual redundancy, it's
probably not the right fit. I'll say so before taking an engagement.

---

## :material-school-outline: Do I need FreeBSD knowledge?

No. The system is documented, deployment is automated, and every operational
task your team will need to perform is covered in a runbook. The goal is
infrastructure you can own, understand, and operate — not one that requires
a specialist every time something needs touching.

---

## :material-alert-circle-outline: What happens if something goes wrong after handover?

Every implementation includes one month of post-launch support. During that
period I monitor closely and respond to any issues.

After that, monthly support clients have a direct line to me during business
hours. For clients who manage it themselves, the documentation covers the
operational tasks you'll actually need to perform.

Hardware failures are handled by the server provider — dedicated server SLAs
typically resolve hardware issues within hours.

---

## :material-scale-balance: What's the minimum scale where this makes sense?

Rough guide: if your cloud bill is above £500 per month, it's worth running
the numbers. Below that, the one-off migration cost may take too long to pay
back.

Not sure? Describe your situation and I'll give you an honest answer before
we go any further.

---

## :material-bank-outline: How do payments work?

I invoice via [Wise](https://wise.com) in GBP or EUR. UK domestic and
international bank transfers both work cleanly. The audit is invoiced upfront.
Implementation is split 50% at the start, 50% on completion. Support is
invoiced monthly.

---

[Book a free call →](https://calendly.com/roman-hypha/call-with-roman){ .md-button .md-button--primary }
[Get in touch →](mailto:infra@hyphatech.io){ .md-button }
