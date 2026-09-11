"""Phase 31: the actual "product metrics dashboard" for this project - a
real, tested CLI report over backend/routes/metrics.py's real aggregation
endpoint, not a web UI. No frontend build tooling exists anywhere in this
environment (apps/ is architecture-only, same honest gap as Phase 18) - a
browser dashboard here would be exactly the kind of never-run code this
project's Engineering Principles refuse to fabricate.

No real device fleet exists either, so by default this reports on whatever
metric events actually exist for a device - which is zero for a fresh
device, and honestly says so, rather than showing fabricated sample data.
tools/performance_sweep.py --report-to can feed this report genuinely real
data (this project's own real pipeline runs), so the numbers shown are
never invented even when no physical fleet backs them.

Requires the `ota` optional dependency group (httpx):
    pip install -e ".[ota]"

Usage:
    python -m tools.metrics_report --base-url http://127.0.0.1:8000 \\
        --token <jwt> --device-id <id>
"""

from __future__ import annotations

import argparse
import sys

import httpx


def render_report(summary: dict) -> str:
    lines = [f"Device {summary['device_id']}: {summary['n_events']} recorded event(s)"]
    if summary["n_events"] == 0:
        lines.append("  (no metric events yet - no real device fleet exists; see docs/roadmap.md's Phase 31 note)")
        return "\n".join(lines)

    lines.append("  status breakdown:")
    for status_name, count in sorted(summary["status_counts"].items(), key=lambda kv: -kv[1]):
        lines.append(f"    {status_name:20s} {count}")

    lines.append("  language pairs:")
    for pair in summary["language_pair_counts"]:
        src = pair["source_language"] or "?"
        tgt = pair["target_language"] or "?"
        lines.append(f"    {src} -> {tgt:20s} {pair['count']}")

    if summary["avg_latency_ms"] is not None:
        lines.append(
            f"  latency: avg={summary['avg_latency_ms']}ms "
            f"p50={summary['p50_latency_ms']}ms p95={summary['p95_latency_ms']}ms"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="JWT from POST /auth/login")
    parser.add_argument("--device-id", required=True)
    args = parser.parse_args()

    with httpx.Client() as client:
        resp = client.get(
            f"{args.base_url}/devices/{args.device_id}/metrics/summary",
            headers={"Authorization": f"Bearer {args.token}"},
        )
        if resp.status_code != 200:
            print(f"failed to fetch summary: {resp.status_code} {resp.text}", file=sys.stderr)
            return 1
        print(render_report(resp.json()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
