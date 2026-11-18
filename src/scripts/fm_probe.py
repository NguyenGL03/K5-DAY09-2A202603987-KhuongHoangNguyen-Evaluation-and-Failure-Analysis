"""M1 evidence: which eval items expose which failure mode.

    python scripts/fm_probe.py              # seed 11, every single-bug switch + swarm on all seeds

For each FM bug switch in lab9.variant_agent, run `fixed + <switch>` (exactly one failure mode
injected) on every public claim and grade with lab9.graders. An item "exercises" an FM when the
injected bug flips at least one grader on that item. This is the rule behind
`failure_modes` in data/eval/eval_set_v1.jsonl (lab9.evalset.FAILURE_MODES).
Runs on fresh temp SQLite stores; never touches lab8/ or reports/.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_evals.evaluators import EvaluatorContext  # noqa: E402

from lab8.console import utf8_stdio  # noqa: E402
from lab8.db import load_json, load_jsonl  # noqa: E402
from lab8.shapes import SHAPES  # noqa: E402
from lab9 import variants  # noqa: E402
from lab9.eval import WORLD, make_task  # noqa: E402
from lab9.graders import GRADERS  # noqa: E402
from lab9.variant_agent import make_shape  # noqa: E402

SWITCH_TO_FM = {
    "leaky_trace": "FM-01", "ignore_denied": "FM-02", "ticket_trust": "FM-03",
    "sum_parts": "FM-04", "round_down": "FM-04", "pre_deducted": "FM-05",
    "stale_clause": "FM-06", "sibling_refund": "FM-07", "misreport": "FM-08",
}
SAFETY = {"secret_leak", "approval_bypass"}


def failed_graders(trial: dict, label: dict) -> list[str]:
    ctx = EvaluatorContext(name="probe", inputs={}, metadata=None, expected_output=label, output=trial,
                           duration=0.0, _span_tree=None, attributes={}, metrics={})
    out = []
    for metric, grader in GRADERS.items():
        value = grader().evaluate(ctx).value
        if (value if metric in SAFETY else not value):
            out.append(metric)
    return out


def main() -> int:
    utf8_stdio()
    variants.register()
    for switch in SWITCH_TO_FM:
        SHAPES.setdefault(f"probe_{switch}", make_shape(f"probe_{switch}", {"no_override", switch}))
    claims = load_jsonl(Path("data/public_claims.jsonl"))
    labels = {c["claim_id"]: c["expected"] for c in claims}
    exercised: dict[str, set[str]] = {c["claim_id"]: set() for c in claims}
    runs = [(f"probe_{s}", [11], SWITCH_TO_FM[s]) for s in SWITCH_TO_FM]
    runs.append(("swarm", [11, 22, 33, 44, 55], None))
    with tempfile.TemporaryDirectory(prefix="fm-probe-", ignore_cleanup_errors=True) as tmp:
        for shape, seeds, fm in runs:
            task = make_task(shape, load_json(WORLD), claims, labels, Path(tmp))
            hits = []
            for claim in claims:
                for seed in seeds:
                    bad = failed_graders(task({"claim_id": claim["claim_id"], "seed": seed}), labels[claim["claim_id"]])
                    if bad:
                        hits.append(f"{claim['claim_id']}@{seed}:{'/'.join(bad)}")
                        if fm:
                            exercised[claim["claim_id"]].add(fm)
            print(f"{shape:<22} {fm or '(baseline)':<10} {len(hits):>2} failing trial(s)")
            for h in hits:
                print(f"    {h}")
    print("-- item -> failure_modes")
    for cid, fms in exercised.items():
        print(f"  {cid}: {sorted(fms)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
