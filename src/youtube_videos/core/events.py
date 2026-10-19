"""Best-effort ZeroMQ notifications. Database always commits before publication."""
from __future__ import annotations
import json


class Publisher:
    def __init__(self, config: dict):
        self.topic = config.get("topic", "youtube-videos.v1")
        self.socket = None
        self.context = None
        if config.get("enabled", False):
            try:
                import zmq
            except ImportError as e:
                raise RuntimeError("Install the [zmq] extra to enable broadcasting") from e
            self.context = zmq.Context.instance()
            self.socket = self.context.socket(zmq.PUB)
            self.socket.setsockopt(zmq.SNDHWM, 100)
            self.socket.setsockopt(zmq.LINGER, 0)
            if config.get("bind", True):
                self.socket.bind(config["address"])
            else:
                self.socket.connect(config["address"])

    def publish(self, event: dict):
        if self.socket is None:
            return
        try:
            import zmq
            self.socket.send_multipart([self.topic.encode(), json.dumps(event).encode()], flags=zmq.NOBLOCK)
        except zmq.Again:
            pass  # Database event remains replayable.

    def close(self):
        if self.socket is not None:
            self.socket.close(linger=0)
