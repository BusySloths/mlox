---
slug: operator-demo
title: "MLOX Operations: catching a silent model failure, live"
type: demo
status: draft
# Narrated slide video: one chapter per deck slide, in deck order.
# Rendered by content/operator-demo/video.py into content/.work/operator-demo/operator-demo.mp4.
voice: gpt-4o-mini-tts/onyx
---

# MLOX Operations: catching a silent model failure, live

Narration for the deck in `content/operator-demo/deck/`. Each chapter is one
slide; the blockquote is spoken while the slide is on screen. Keep the wording
consistent with the deck: two-step Reasonable AI, early detection first, then a
reasoning model; critical actions wait for a person.

## Chapter: title

> A model in production can fail without a single error. This is MLOX catching
> exactly that, live, on real infrastructure: the broken step found in seconds,
> explained by a reasoning model, and a person deciding what happens next.

## Chapter: acts

> The demo has four acts. We set up the users and the operator, let MLOX learn
> what normal looks like, break one step inside the model, and then watch MLOX
> detect it, investigate it, and recover.

## Chapter: setup

> On the left, a traffic simulator plays the users, sending prediction requests
> every two seconds. It also has a hidden corruption switch. On the right is the
> MLOX terminal UI: the operator's control room.

## Chapter: services

> Five services, all deployed and wired together by MLOX. The model is served by
> an MLflow Gateway on Kubernetes. It loads its champion from the MLflow
> registry, gets its credentials from OpenBao, and sends a trace for every
> request through OpenTelemetry into InfluxDB. Nobody copied a URL or a
> password.

## Chapter: operations

> The Operations view is where the watching happens. Pick the telemetry source
> and press Start Watching. The reasoning model sits in a pluggable slot, and
> its key stays in the project's secret store.

## Chapter: start

> Watching starts from a clean slate. The traffic begins, and with the first
> complete trace, the pipeline appears.

## Chapter: pipelines

> MLOX discovers the pipeline from the traces themselves: four steps, from
> normalizing the input to evaluating the error. Nobody draws it by hand. On
> top of it, Reasonable AI works in two steps. Early-detection models watch
> every step within seconds, and a reasoning model investigates as soon as an
> incident is raised.

## Chapter: calibrate

> Ten normal runs become the baseline. From now on, every request is compared
> with it, step by step. All four steps are normal, and the prediction error
> sits at about zero point zero two.

## Chapter: break

> Now we break it. One command shifts a component inside the PCA step. Every
> request still returns two hundred, OK. Only the answers are wrong, and MLOX is
> never told about the fault.

## Chapter: detect

> Two requests later, the pipeline is in incident. MLOX points straight at the
> PCA step: its output jumped from under three to over fourteen, while the step
> before it stayed normal. Downstream, the error climbs a hundredfold.

## Chapter: investigate

> The reasoning model investigates the incident. It confirms the origin with
> numbers, rules out data and infrastructure problems, and proposes rolling the
> model back by one version. A rollback is critical, so it waits for a person
> to approve. Here, we remove the fault instead.

## Chapter: recover

> Fault off. MLOX only calls it recovered once every step is back within its
> baseline, about thirty seconds later. The postmortem goes straight into the
> project's knowledge base.

## Chapter: outlook

> Self-hosted ML with an operator built in: monitoring without setup, the root
> cause in seconds, and boundaries you set. Next come our own efficient
> reasoning models, merging both steps into one. This is MLOX.
