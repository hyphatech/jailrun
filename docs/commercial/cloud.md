---
icon: material/exit-run
---
 
# Leave the Cloud

Modern infrastructure is massively overcomplicated and expensive. Not because
it has to be — because the people selling it need it to be. They create a
problem that didn't exist before, that you never asked about, and then charge
you to solve it.

Over the past decade, the cloud vendors have done an extraordinary job of
making their complexity feel inevitable. Kubernetes for container orchestration.
RDS for managed databases. ElastiCache for Redis. CloudFront for your CDN.
A managed service for every layer of your stack, each one abstracting away
something you could run yourself for a fraction of the cost, each one adding
another line to an invoice that grows in ways that are genuinely difficult to
predict or control.

The result is that most companies — startups, scale-ups, legacy businesses
trying to modernise — are running infrastructure far more complex than their
actual requirements justify, and paying far more than they need to. Not because
anyone made a bad decision, but because the default path leads there, and
nobody stopped to question it.

!!! example "Case study"

    [37signals](https://37signals.com) — the company behind Basecamp and HEY —
    [left the cloud](https://basecamp.com/cloud-exit) in 2023 and now saves
    millions per year. Their co-founder David Heinemeier Hansson has written
    extensively about it. Worth reading.

<div class="avatar-row">
  <img src="../../assets/ava.jpg" alt="Avatar" class="avatar">
</div>

My name is [Roman Zaiev](https://www.linkedin.com/in/zaiev/). I've spent
15 years building production systems at a scale most companies will never
approach. I've seen how much money gets burned daily for literally nothing
just to stay within the boundaries of an existing setup. I've seen how
ridiculously complex modern DevOps has become, even for one-time tasks that
should take hours, not weeks. I've seen enough from different angles to reach
one simple conclusion: I will never go the same way for my own products.

Trusting clouds to run our infrastructure, we trapped ourselves in a
vendor-locked world with unpredictable monthly bills — charged extras for
everything from load spikes to traffic, with cloud architecture leaking so
deeply into our own applications that escape starts to feel impossible.

There must be a different way. Something simpler, more elegant, something that
silently works and doesn't cost a fortune. It exists — it was there all along.
We've just been ignoring it for years.

Our biggest infrastructure win at Hypha wasn't just choosing bare metal over
cloud — that's only part of the story. We also don't use Linux, Docker, or
Kubernetes. Instead, we chose FreeBSD: a system that pioneered jails, the
original practical implementation of what we now call containers, offering
more capability at far lower operational and complexity cost than anything the
modern stack has to offer.

!!! example "Case study"

    [hypha.tv](https://hypha.tv) is a video platform for professional creators,
    with transcoding workers, terabytes of 4K storage, and the kind of egress
    traffic that would make an AWS bill deeply unpleasant. Our monthly
    infrastructure cost is a fraction of what the equivalent managed setup
    would run to. Zero-downtime deployments, simple scaling, automated backups,
    and extensive monitoring are included.

Now I help others take the same path.

---

## Time to talk

If your cloud bill has started to feel like a subscription you can't cancel,
you're probably ready for this conversation. That tends to happen at a
particular moment in a company's life — early on, managed services genuinely
save time and the cost is easy to justify against engineering hours. Then the
product stabilises, the team grows, and suddenly you're paying for things
you never use.

It's also common to inherit infrastructure you didn't design. A previous team
made decisions that made sense at the time, accumulated managed services along
the way, and left behind something expensive and opaque. Reducing that bill
is now someone's problem, and the challenge isn't technical — it's knowing
what to replace it with.

Then there are teams who already know what they want. They know enough to know
that self-hosted bare-metal infrastructure is simpler and cheaper at their
scale, but haven't had the time or the right person to build it properly —
with automation, tested backups, monitoring, a deployment process that doesn't
require heroics, and documentation that survives beyond the person who wrote it.

If any of this describes your situation, the conversation is worth having.

---

## The offer

<div class="grid cards" markdown>

-   :material-file-search-outline: **Infra audit**

    ---

    I review your business requirements and current stack and produce a written
    report with a proposed architecture, realistic monthly cost estimate, and a
    fixed implementation price if you want to proceed.

    Standalone — take it and act on it however you like, with whoever you like.
    The fee is deducted if you proceed to implementation.

    **From £750**

-   :material-server: **Implementation**

    ---

    Scope and price come directly from the audit — you know exactly what you're
    getting before work begins. I provision the servers, configure the full
    stack in FreeBSD jails, set up backups, zero-downtime deployments,
    monitoring, alerting, and daily health summaries. Everything is documented.

    **From £3,000**

-   :material-wrench-outline: **Monthly support**

    ---

    Optional after implementation. A rolling contract with no minimum term —
    cancel with 30 days notice. Direct line to me for updates, patches, and
    anything that needs attention. If you'd rather run it yourselves, the
    documentation is written for that too.

    **From £300 / month**

-   :material-handshake-outline: **Bespoke engagement**

    ---

    Something that doesn't fit a fixed scope — code review, performance
    analysis, architecture consulting, or a second opinion on a hard problem.
    Custom scope, custom price, direct conversation.

    [Get in touch :octicons-arrow-right-24:](mailto:dev@hyphatech.io){ .md-button }

</div>

[Full details on services and pricing →](services.md)

---

## The numbers

A typical small production stack on AWS — an application server, managed
Postgres, Redis, a load balancer, S3 for storage — runs to £300–1,500 per
month. Add meaningful egress traffic and it climbs further: AWS charges
per gigabyte out, and it adds up faster than most teams expect.

The equivalent on two bare-metal servers runs to £100–200 per month, with
unmetered traffic included as standard. For companies with significant egress
— video, file storage, data-heavy APIs — the bandwidth saving alone often
exceeds the entire server bill.

If you're currently paying £2,000 per month, a migration typically reduces
that to £150–250. The one-off cost of audit and implementation pays for
itself within the first two to three months. Every month after that is direct
saving.

If the numbers don't work out that way for your situation, I'll tell you in
the audit rather than take your money.

---

<div class="grid cards" markdown>

-   :material-calendar: **Book a free call**

    A 30-minute conversation. I'll look at your current setup and give you
    an honest picture of what's possible and what it would cost.

    [Book via Calendly :octicons-arrow-right-24:](https://calendly.com/roman-hypha/call-with-roman){ .md-button .md-button--primary }

-   :material-email-outline: **Not a call person?**

    Send me a description of your stack and what you're currently paying.
    I'll respond with an honest assessment within one business day.

    [Get in touch :octicons-arrow-right-24:](mailto:infra@hyphatech.io){ .md-button }

</div>

**Fixed prices. No surprises.**
