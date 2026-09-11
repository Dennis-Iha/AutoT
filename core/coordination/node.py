"""Phase 16: dual-earbud coordination - master election, failure detection,
automatic promotion, battery-aware role selection.

Critical requirement from the master spec, enforced by this design: no
earbud may depend on the OTHER one for its own translation capability.
Each ``EarbudNode`` starts and falls back to ``Role.STANDALONE`` (full
independent capability - the same single-node pipeline Phase 8 already
proved) whenever no peer is present; MASTER/SECONDARY only exists as an
optimization when both are connected, never a requirement.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, replace
from enum import Enum

from core.coordination.channel import Channel


class Role(str, Enum):
    STANDALONE = "standalone"  # no peer connected - this node is a complete AT device alone
    MASTER = "master"
    SECONDARY = "secondary"


@dataclass(frozen=True)
class DeviceHealth:
    battery_pct: float = 100.0
    temperature_c: float = 25.0
    signal_quality: float = 1.0  # 0-1, higher is better
    processing_load: float = 0.0  # 0-1, lower is better

    def fitness_score(self) -> float:
        """Higher = better master candidate. Weights the criteria the master
        spec names explicitly (battery, connectivity, compute availability,
        temperature, device health) - weights are a reasonable starting
        design, not derived from any real device measurement (none exists)."""
        temp_penalty = max(0.0, (self.temperature_c - 25.0) / 50.0)
        return (
            0.4 * (self.battery_pct / 100.0)
            + 0.25 * self.signal_quality
            + 0.20 * (1.0 - self.processing_load)
            - 0.15 * temp_penalty
        )


class EarbudNode:
    def __init__(
        self,
        node_id: str,
        channel: Channel,
        peer_timeout_s: float = 3.0,
        health: DeviceHealth | None = None,
    ):
        self.node_id = node_id
        self.channel = channel
        self.peer_timeout_s = peer_timeout_s
        self.role = Role.STANDALONE
        self.health = health or DeviceHealth()
        self.peer_node_id: str | None = None
        self.peer_health: DeviceHealth | None = None
        self._last_peer_heartbeat_at: float | None = None

    def update_health(self, **kwargs) -> None:
        self.health = replace(self.health, **kwargs)

    def send_heartbeat(self) -> None:
        self.channel.send({
            "type": "heartbeat",
            "node_id": self.node_id,
            "health": asdict(self.health),
        })

    def poll(self, now: float | None = None) -> None:
        """Non-blocking: drains any pending messages, updates peer state,
        detects peer loss via timeout, and re-runs election. Call
        periodically (e.g. once per heartbeat interval)."""
        now = now if now is not None else time.monotonic()

        msg = self.channel.receive(timeout_s=0.0)
        while msg is not None:
            self._handle_message(msg, now)
            msg = self.channel.receive(timeout_s=0.0)

        if (
            self._last_peer_heartbeat_at is not None
            and now - self._last_peer_heartbeat_at > self.peer_timeout_s
        ):
            self._on_peer_lost()

        self._elect()

    def _handle_message(self, msg: dict, now: float) -> None:
        if msg.get("type") == "heartbeat":
            self.peer_node_id = msg["node_id"]
            self.peer_health = DeviceHealth(**msg["health"])
            self._last_peer_heartbeat_at = now

    def _on_peer_lost(self) -> None:
        self.peer_node_id = None
        self.peer_health = None
        self._last_peer_heartbeat_at = None

    def _elect(self) -> None:
        if self.peer_health is None:
            self.role = Role.STANDALONE
            return
        my_fitness = self.health.fitness_score()
        peer_fitness = self.peer_health.fitness_score()
        if my_fitness > peer_fitness:
            self.role = Role.MASTER
        elif my_fitness < peer_fitness:
            self.role = Role.SECONDARY
        else:
            # Deterministic tie-break so both sides agree without a 3rd
            # party - lexicographically smaller node_id wins.
            assert self.peer_node_id is not None
            self.role = Role.MASTER if self.node_id < self.peer_node_id else Role.SECONDARY
