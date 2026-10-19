---
title: "Event-Driven Pipelines From First Principles"
description: "A tiny demonstration chapter for reproducible draft creation"
---

# Event-Driven Pipelines

A producer emits an event without directly invoking consumers. A separate consumer reads the event and decides what to do.

## Publish and subscribe

The publisher and consumer communicate through an event channel. The consumer must tolerate messages arriving late.

```python
messages = ["event.created", "event.checked"]
for message in messages:
    print(message)
```

## Review the output

Check the events emitted by the program. The pipeline does not claim the code was executed; that requires a separate verified execution stage.

Read the [ZeroMQ Guide](https://zguide.zeromq.org/) before adding distributed workers.
