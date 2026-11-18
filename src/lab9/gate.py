"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item

SAFETY_COUNTS = ("secret_leak", "approval_bypass")   # aggregated as a count, like lab9.eval.aggregate
TOL = 1e-3                                            # reports round metrics to 4 decimals


def _is_bad_number(v) -> bool:
    return isinstance(v, float) and (math.isnan(v) or math.isinf(v))


def _graded_ids(spec: dict) -> list[str]:
    from lab9.graders import GRADERS
    return [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]


def _report_problems(rep: dict, spec: dict, who: str) -> list[str]:
    """Self-consistency of ONE report: numbers, row count, duplicates, crashed graders, and
    metrics that do not follow from its own rows (hand-edited or recomputed on a subset)."""
    out: list[str] = []
    metrics, rows, man = rep.get("metrics") or {}, rep.get("rows") or [], rep.get("manifest") or {}
    out += [f"{who} metric {k} is {v!r} (NaN/inf)" for k, v in metrics.items() if _is_bad_number(v)]
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{who} has {len(rows)} rows, manifest says {man.get('items')} items x "
                   f"{len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dup = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dup:
        out.append(f"{who} has duplicated (item, seed) rows: {dup[:5]}")
    stray = sorted({r.get("seed") for r in rows} - set(man.get("seeds") or []), key=str)
    if stray:
        out.append(f"{who} rows use seeds {stray} not in its manifest")
    if rep.get("evaluator_failures"):
        out.append(f"{who} has {len(rep['evaluator_failures'])} evaluator failure(s): "
                   f"{rep['evaluator_failures'][0]}")
    for mid in _graded_ids(spec):
        missing = [f"{r.get('item_id')}@{r.get('seed')}" for r in rows if r.get(mid) is None]
        if missing:
            out.append(f"{who} metric {mid} has no value on {len(missing)} row(s), e.g. {missing[0]} "
                       f"(crashed grader dropped out of the mean)")
            continue
        got = metrics.get(mid)
        if rows and isinstance(got, (int, float)) and not _is_bad_number(got):
            vals = [r[mid] for r in rows]
            again = sum(vals) if mid in SAFETY_COUNTS else sum(vals) / len(vals)
            if abs(float(got) - again) > TOL:
                out.append(f"{who} metric {mid} = {got} but its rows give {again:.4f}")
    by_item: dict[str, list[bool]] = {}
    for r in rows:
        if "pass_rate" in r:
            by_item.setdefault(r["item_id"], []).append(bool(r["pass_rate"]))
    if by_item and len({len(v) for v in by_item.values()}) == 1:
        n = len(next(iter(by_item.values())))
        checks = {"pass_5": lambda v: float(all(v))}
        for k in spec.get("pass_k") or []:
            if 1 <= k <= n:
                checks[f"pass_at_{k}"] = lambda v, k=k: stats.pass_at_k(len(v), sum(v), k)
                checks[f"pass_hat_{k}"] = lambda v, k=k: stats.pass_hat_k(len(v), sum(v), k)
        for name, fn in checks.items():
            got = metrics.get(name)
            if isinstance(got, (int, float)) and not _is_bad_number(got):
                again = sum(fn(v) for v in by_item.values()) / len(by_item)
                if abs(float(got) - again) > TOL:
                    out.append(f"{who} metric {name} = {got} but its rows give {again:.4f}")
    return out


def _looser(th_new: dict, th_old: dict) -> list[str]:
    """Ways th_new is laxer than th_old (empty = same or stricter)."""
    out = []
    if "max" in th_old and not ("max" in th_new and th_new["max"] <= th_old["max"]):
        out.append(f"max {th_old['max']} -> {th_new.get('max', 'removed')}")
    if "min" in th_old and not ("min" in th_new and th_new["min"] >= th_old["min"]):
        out.append(f"min {th_old['min']} -> {th_new.get('min', 'removed')}")
    if "max_increase" in th_old and not ("max_increase" in th_new
                                         and th_new["max_increase"] <= th_old["max_increase"]):
        out.append(f"max_increase {th_old['max_increase']} -> {th_new.get('max_increase', 'removed')}")
    if th_old.get("no_significant_drop") and not th_new.get("no_significant_drop"):
        out.append("no_significant_drop dropped")
    return out


def ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Same eval-set version => thresholds may only get stricter (metrics AND slices)."""
    if spec.get("eval_set_version") != base_spec.get("eval_set_version"):
        return []
    out = []
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        cur = new_m.get(m["id"])
        if cur is None:
            out.append(f"ratchet: metric {m['id']} removed")
            continue
        if m.get("blocking") and not cur.get("blocking"):
            out.append(f"ratchet: metric {m['id']} no longer blocking")
        out += [f"ratchet: metric {m['id']} {w}" for w in _looser(cur.get("threshold") or {}, m.get("threshold") or {})]
    new_s = {(x["name"], x["metric"]): x for x in spec.get("slices") or []}
    for x in base_spec.get("slices") or []:
        sid = f"slice:{x['name']}/{x['metric']}"
        cur = new_s.get((x["name"], x["metric"]))
        if cur is None:
            out.append(f"ratchet: {sid} removed")
            continue
        if x.get("blocking") and not cur.get("blocking"):
            out.append(f"ratchet: {sid} no longer blocking")
        out += [f"ratchet: {sid} {w}" for w in _looser(cur, x)]
    return out


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = _report_problems(pr, spec, "PR") + _report_problems(base, spec, "baseline")
    pr_keys = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if pr_keys != base_keys:
        gone, extra = sorted(base_keys - pr_keys, key=str), sorted(pr_keys - base_keys, key=str)
        problems.append(f"(item, seed) set differs from baseline: {len(gone)} missing {gone[:3]}, "
                        f"{len(extra)} extra {extra[:3]}")
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    if sorted(pm.get("seeds") or []) != sorted(bm.get("seeds") or []) or pm.get("items") != bm.get("items"):
        problems.append(f"manifest differs from baseline: items {pm.get('items')} vs {bm.get('items')}, "
                        f"seeds {pm.get('seeds')} vs {bm.get('seeds')}")
    pr_tags: dict[str, frozenset] = {}
    for r in pr.get("rows") or []:
        tags = frozenset(r.get("slices") or [])
        if pr_tags.setdefault(r["item_id"], tags) != tags:
            problems.append(f"{r['item_id']}: slice tags differ between its own rows")
    base_tags = {r["item_id"]: frozenset(r.get("slices") or []) for r in base.get("rows") or []}
    problems += [f"{i}: slice tags {sorted(t)} differ from baseline {sorted(base_tags[i])}"
                 for i, t in sorted(pr_tags.items()) if i in base_tags and t != base_tags[i]]
    if base_spec is not None:
        problems += ratchet_problems(spec, base_spec)
        if (spec.get("eval_set_version") != base_spec.get("eval_set_version")
                and pm.get("eval_set_sha") == bm.get("eval_set_sha")):
            problems.append("ratchet: eval_set_version bumped but the eval set (sha) is unchanged")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for x in spec.get("slices") or []:
        name, mid = x["name"], x["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            verdict = "missing"                  # an empty slice cannot vouch for anything
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in x and val < x["min"]:
                verdict = "fail"
            if x.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                   n_resamples=bs.get("n_resamples", 1000),
                                                   rng=bs.get("rng", 2027))
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}] n={len(keys)}"
                if hi < 0:
                    verdict = "fail"
        if verdict != "ok" and x.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if x.get("blocking") else "warn")
        th = {k: x[k] for k in ("min", "no_significant_drop") if k in x}
        lines.append(f"  {sid:<38} {val!s:<8} {json.dumps(th):<40} {note:<34} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
