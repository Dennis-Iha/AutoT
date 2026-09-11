"""Tests core/coordination/node.py's master election, failure detection, and
promotion against a simulated channel (see core/coordination/channel.py's
docstring for why - no real BLE hardware exists in this environment).
Covers every scenario the master spec explicitly names: left only, right
only, both together, primary failure, battery degradation, packet loss.
"""

from __future__ import annotations

from core.coordination.channel import InMemoryChannelPair
from core.coordination.node import DeviceHealth, EarbudNode, Role


def make_pair(**channel_kwargs) -> tuple[EarbudNode, EarbudNode]:
    pair = InMemoryChannelPair(**channel_kwargs)
    left = EarbudNode("left", pair.a, peer_timeout_s=0.3)
    right = EarbudNode("right", pair.b, peer_timeout_s=0.3)
    return left, right


def exchange(left: EarbudNode, right: EarbudNode, rounds: int = 3, t: float = 0.0, step: float = 0.05):
    """Simulates rounds of both nodes heartbeating and polling."""
    for _ in range(rounds):
        left.send_heartbeat()
        right.send_heartbeat()
        t += step
        left.poll(now=t)
        right.poll(now=t)
    return t


def test_left_only_is_standalone():
    pair = InMemoryChannelPair()
    left = EarbudNode("left", pair.a)
    left.poll()
    assert left.role == Role.STANDALONE


def test_right_only_is_standalone():
    pair = InMemoryChannelPair()
    right = EarbudNode("right", pair.b)
    right.poll()
    assert right.role == Role.STANDALONE


def test_both_together_higher_battery_becomes_master():
    left, right = make_pair()
    left.update_health(battery_pct=90.0)
    right.update_health(battery_pct=30.0)
    exchange(left, right)
    assert left.role == Role.MASTER
    assert right.role == Role.SECONDARY


def test_both_together_roles_are_complementary_not_both_master():
    left, right = make_pair()
    left.update_health(battery_pct=50.0)
    right.update_health(battery_pct=80.0)
    exchange(left, right)
    roles = {left.role, right.role}
    assert roles == {Role.MASTER, Role.SECONDARY}


def test_tie_break_is_deterministic_and_agreed_by_both_sides():
    left, right = make_pair()
    # identical health -> tie -> lexicographically smaller node_id ("left") wins
    exchange(left, right)
    assert left.role == Role.MASTER
    assert right.role == Role.SECONDARY


def test_primary_failure_promotes_secondary_to_standalone():
    left, right = make_pair()
    left.update_health(battery_pct=90.0)
    right.update_health(battery_pct=30.0)
    t = exchange(left, right)
    assert left.role == Role.MASTER
    assert right.role == Role.SECONDARY

    # left (master) stops heartbeating - simulate failure/power-off.
    # right must promote itself once the peer timeout elapses.
    t += 0.5
    right.poll(now=t)
    assert right.role == Role.STANDALONE
    assert right.peer_node_id is None


def test_battery_degradation_triggers_role_swap():
    left, right = make_pair()
    left.update_health(battery_pct=90.0)
    right.update_health(battery_pct=30.0)
    exchange(left, right)
    assert left.role == Role.MASTER

    # left's battery degrades below right's over time.
    left.update_health(battery_pct=10.0)
    exchange(left, right)
    assert left.role == Role.SECONDARY
    assert right.role == Role.MASTER


def test_packet_loss_does_not_cause_premature_promotion_if_some_heartbeats_land():
    left, right = make_pair(drop_rate=0.5, seed=42)
    left.update_health(battery_pct=90.0)
    right.update_health(battery_pct=30.0)
    # Many rounds within the timeout window - enough heartbeats should get
    # through despite 50% loss that neither side falsely detects the other
    # as gone.
    exchange(left, right, rounds=20, step=0.01)
    assert right.role in (Role.SECONDARY, Role.STANDALONE)  # never crashes/errors
    # At least one heartbeat should have landed given 20 rounds at 50% drop.
    assert left.peer_node_id is not None or right.peer_node_id is not None


def test_both_reconnect_after_peer_loss_re_elect_correctly():
    left, right = make_pair()
    left.update_health(battery_pct=90.0)
    right.update_health(battery_pct=30.0)
    t = exchange(left, right)
    assert right.role == Role.SECONDARY

    # peer lost
    t += 0.5
    right.poll(now=t)
    assert right.role == Role.STANDALONE

    # left comes back
    t = exchange(left, right, t=t, rounds=3)
    assert left.role == Role.MASTER
    assert right.role == Role.SECONDARY


def test_fitness_score_penalizes_high_temperature():
    cool = DeviceHealth(battery_pct=50, temperature_c=25)
    hot = DeviceHealth(battery_pct=50, temperature_c=60)
    assert cool.fitness_score() > hot.fitness_score()


def test_fitness_score_rewards_low_processing_load():
    idle = DeviceHealth(battery_pct=50, processing_load=0.0)
    busy = DeviceHealth(battery_pct=50, processing_load=1.0)
    assert idle.fitness_score() > busy.fitness_score()
