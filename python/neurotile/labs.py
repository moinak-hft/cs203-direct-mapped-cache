"""Small reproducible architecture experiments, independent of the AI accelerator.

Addresses in these experiments are cache-line addresses, not CPU instructions.
All reported cycle counts belong to the documented model, not to a RISC-V CPU.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import random
from typing import Any


POLICIES = ("off", "next_line", "stride")
FEATURES = ("unit_delta", "dominant_delta", "reuse", "stride_abs")
CACHE_LINES = 16
MEMORY_LATENCY = 12
COMPUTE_CYCLES = 8
WINDOW = 32


def trace_features(lines: list[int]) -> list[int]:
    """Integer features from the *previous* demand window, with scale 0..255."""
    if len(lines) < 2:
        return [0, 0, 0, 0]
    deltas = [b - a for a, b in zip(lines, lines[1:])]
    delta, count = Counter(deltas).most_common(1)[0]
    return [
        255 * deltas.count(1) // len(deltas),
        255 * count // len(deltas),
        255 * (len(lines) - len(set(lines))) // len(lines),
        min(255, abs(delta)),
    ]


def rule_policy(features: list[int]) -> str:
    """Simple non-ML baseline; constants are deliberately fixed in advance."""
    unit, consistency, reuse, stride = features
    if reuse >= 64:
        return "off"
    if unit >= 192:
        return "next_line"
    if consistency >= 192 and stride > 0:
        return "stride"
    return "off"


@dataclass
class Tree:
    prediction: int
    feature: int = -1
    threshold: int = 0
    left: Any = None
    right: Any = None

    def predict(self, features: list[int]) -> int:
        if self.feature < 0:
            return self.prediction
        branch = self.left if features[self.feature] <= self.threshold else self.right
        return branch.predict(features)

    def as_dict(self) -> dict:
        if self.feature < 0:
            return {"policy": POLICIES[self.prediction], "policy_id": self.prediction}
        return {
            "feature": FEATURES[self.feature], "feature_index": self.feature,
            "threshold": self.threshold, "left": self.left.as_dict(),
            "right": self.right.as_dict(),
        }


def _fit_tree(rows: list[tuple[list[int], int]], depth: int = 3) -> Tree:
    """Deterministic small CART classifier, Gini splits, no dependencies."""
    counts = Counter(label for _, label in rows)
    prediction = min(counts, key=lambda label: (-counts[label], label))
    node = Tree(prediction)
    if depth == 0 or len(counts) == 1 or len(rows) < 4:
        return node

    def impurity(part: list[tuple[list[int], int]]) -> float:
        total = len(part)
        return total - sum(n * n for n in Counter(y for _, y in part).values()) / total

    parent_cost = impurity(rows)
    best = None
    for feature in range(len(FEATURES)):
        values = sorted({x[feature] for x, _ in rows})
        for threshold in values[:-1]:
            left = [row for row in rows if row[0][feature] <= threshold]
            right = [row for row in rows if row[0][feature] > threshold]
            if min(len(left), len(right)) < 2:
                continue
            cost = impurity(left) + impurity(right)
            candidate = (cost, feature, threshold)
            if best is None or candidate < best[:3]:
                best = (cost, feature, threshold, left, right)
    if best and best[0] < parent_cost - 1e-12:
        _, node.feature, node.threshold, left, right = best
        node.left, node.right = _fit_tree(left, depth - 1), _fit_tree(right, depth - 1)
        if node.left.feature < 0 and node.right.feature < 0 and node.left.prediction == node.right.prediction:
            return Tree(node.left.prediction)
    return node


def simulate_cache(lines: list[int], policy: str = "off", *, tree: Tree | None = None,
                   cache_lines: int = CACHE_LINES) -> dict:
    """Direct-mapped cache, one outstanding read, demand/prefetch same port.

    Each demand costs one lookup cycle, then eight compute cycles. A memory
    read takes twelve cycles. Prefetches overlap compute; an unrelated pending
    read delays a demand miss. Adaptive selection occurs once per 32 demands.
    """
    if cache_lines < 1:
        raise ValueError("cache_lines must be positive")
    if policy not in (*POLICIES, "rule", "learned"):
        raise ValueError(f"unknown policy: {policy}")
    if policy == "learned" and tree is None:
        raise ValueError("learned policy needs a trained tree")
    tags: list[int | None] = [None] * cache_lines
    unused_prefetch = [False] * cache_lines
    now = hits = demand_reads = prefetch_reads = useful = stalls = 0
    pending: tuple[int, int] | None = None
    last_line = last_delta = None
    selected = "off" if policy in ("rule", "learned") else policy
    decisions = []

    def fill(line: int, prefetched: bool) -> None:
        slot = line % cache_lines
        tags[slot], unused_prefetch[slot] = line, prefetched

    for index, line in enumerate(lines):
        if index and index % WINDOW == 0 and policy in ("rule", "learned"):
            features = trace_features(lines[index - WINDOW:index])
            selected = (POLICIES[tree.predict(features)] if tree else rule_policy(features))
            decisions.append({"start": index, "policy": selected, "features": features})
        if pending is not None and pending[1] <= now:
            fill(pending[0], True)
            pending = None
        slot = line % cache_lines
        if tags[slot] == line:
            hits += 1
        else:
            if pending is not None:
                wait = max(0, pending[1] - now)
                now += wait
                stalls += wait
                fill(pending[0], True)
                pending = None
            if tags[slot] != line:
                now += MEMORY_LATENCY
                stalls += MEMORY_LATENCY
                demand_reads += 1
                fill(line, False)
        if unused_prefetch[slot]:
            useful += 1
            unused_prefetch[slot] = False
        now += 1
        delta = None if last_line is None else line - last_line
        target = None
        if selected == "next_line":
            target = line + 1
        elif selected == "stride" and delta is not None and delta == last_delta and delta != 0:
            target = line + delta
        if target is not None and target >= 0 and pending is None and tags[target % cache_lines] != target:
            pending = (target, now + MEMORY_LATENCY)
            prefetch_reads += 1
        last_line, last_delta = line, delta
        now += COMPUTE_CYCLES
    accesses = len(lines)
    return {
        "policy": policy, "accesses": accesses, "cycles": now, "stall_cycles": stalls,
        "hits": hits, "misses": accesses - hits,
        "hit_rate": hits / accesses if accesses else 0.0,
        "demand_reads": demand_reads, "prefetch_reads": prefetch_reads,
        "memory_transactions": demand_reads + prefetch_reads,
        "useful_prefetches": useful,
        "prefetch_accuracy": useful / prefetch_reads if prefetch_reads else None,
        "decisions": decisions,
    }


def simulate_scratchpad(lines: list[int], capacity: int = CACHE_LINES) -> dict:
    """Known-schedule explicit tiles; charge every line load, no DMA overlap."""
    if capacity < 1:
        raise ValueError("capacity must be positive")
    tiles = loads = 0
    start = 0
    while start < len(lines):
        resident: set[int] = set()
        end = start
        while end < len(lines) and (lines[end] in resident or len(resident) < capacity):
            resident.add(lines[end])
            end += 1
        loads += len(resident)
        tiles += 1
        start = end
    return {
        "policy": "scheduled_scratchpad", "accesses": len(lines),
        "cycles": loads * MEMORY_LATENCY + len(lines) * (1 + COMPUTE_CYCLES),
        "memory_transactions": loads, "tiles": tiles,
        "assumption": "Software knows the address schedule and explicitly preloads each bounded tile; copies are charged and do not overlap compute.",
    }


def _workload(kind: str, seed: int, length: int = 256) -> list[int]:
    rng = random.Random(seed)
    base = rng.randrange(256, 2048)
    if kind == "stream":
        return [base + index for index in range(length)]
    if kind == "stride":
        step = rng.choice((2, 3, 5, 7))
        return [base + step * index for index in range(length)]
    if kind == "reverse":
        return [base + length - index for index in range(length)]
    if kind == "hot":
        return [base + rng.randrange(8) for _ in range(length)]
    if kind == "random":
        return [base + rng.randrange(512) for _ in range(length)]
    if kind == "conflict":
        return [base + CACHE_LINES * (index % 4) for index in range(length)]
    if kind == "phases":
        kinds = ("stream", "random", "stride", "hot")
        quarter = length // len(kinds)
        result = []
        for offset, part in enumerate(kinds):
            result.extend(_workload(part, seed + offset * 997, quarter))
        return result[:length]
    raise ValueError(kind)


def train_prefetch_tree(seed: int = 7) -> tuple[Tree, dict]:
    rows = []
    traces = []
    for kind in ("stream", "stride", "reverse", "hot", "random", "phases"):
        for variant in range(8):
            trace_seed = seed * 1009 + variant * 73 + sum(map(ord, kind))
            lines = _workload(kind, trace_seed)
            traces.append(f"train/{kind}/{variant}")
            for start in range(WINDOW, len(lines), WINDOW):
                previous, upcoming = lines[start - WINDOW:start], lines[start:start + WINDOW]
                # Oracle labels are computed offline; inference never sees upcoming addresses.
                costs = [simulate_cache(upcoming, candidate)["cycles"] for candidate in POLICIES]
                label = min(range(len(POLICIES)), key=lambda i: (costs[i], i))
                rows.append((trace_features(previous), label))
    tree = _fit_tree(rows, depth=3)
    return tree, {
        "algorithm": "CART / Gini", "max_depth": 3, "rows": len(rows),
        "trace_ids": traces, "label": "Lowest modeled cycles among off/next-line/stride on the following cold-cache window; ties prefer off, then next-line.",
        "features": list(FEATURES),
        "training_accuracy": sum(tree.predict(x) == y for x, y in rows) / len(rows),
    }


def run_memory_lab(seed: int = 7) -> dict:
    tree, training = train_prefetch_tree(seed)
    workloads = []
    correct = total = 0
    totals = {name: {"cycles": 0, "memory_transactions": 0} for name in (*POLICIES, "rule", "learned", "scratchpad")}
    for index, kind in enumerate(("stream", "stride", "reverse", "hot", "random", "phases", "conflict")):
        trace_seed = 1_000_003 + seed * 313 + index * 311
        lines = _workload(kind, trace_seed, 384)
        results = {name: simulate_cache(lines, name, tree=tree) for name in (*POLICIES, "rule", "learned")}
        results["scratchpad"] = simulate_scratchpad(lines)
        for name, result in results.items():
            for metric in ("cycles", "memory_transactions"):
                totals[name][metric] += result[metric]
        for start in range(WINDOW, len(lines), WINDOW):
            costs = [simulate_cache(lines[start:start + WINDOW], candidate)["cycles"] for candidate in POLICIES]
            oracle = min(range(len(POLICIES)), key=lambda i: (costs[i], i))
            correct += tree.predict(trace_features(lines[start - WINDOW:start])) == oracle
            total += 1
        workloads.append({"id": f"test/{kind}/0", "kind": kind, "trace_seed": trace_seed,
                          "trace_preview": lines[:16], "results": results})
    off_cycles = totals["off"]["cycles"]
    for result in totals.values():
        result["speedup_vs_off"] = off_cycles / result["cycles"]
    return {
        "lab": "memory", "seed": seed,
        "model": {"cache": "16-line direct mapped", "line_bytes": 16,
                  "capacity_bytes": 256, "lookup_cycles": 1,
                  "memory_read_cycles": MEMORY_LATENCY, "compute_gap_cycles": COMPUTE_CYCLES,
                  "outstanding_prefetches": 1, "selection_window": WINDOW,
                  "timing": "Prefetch reads overlap compute; demand misses wait for a busy memory port. Final issued reads count as traffic even if unused."},
        "training": {**training, "tree": tree.as_dict(), "test_rows": total,
                     "held_out_accuracy": correct / total,
                     "split": "Entire generated traces held out with disjoint seeds and lengths. Six families overlap training; the conflict family is held out entirely."},
        "workloads": workloads, "summary": totals,
        "limitations": ["Synthetic line traces, not executed CPU programs or measured FPGA latency.",
                        "The adaptive policy uses only the preceding window and can lose at phase boundaries.",
                        "Scratchpad assumes a known software schedule; this is unsuitable for unknown pointer chains.",
                        "The RTL selector implements the deterministic seed-7 learned tree; Python can retrain other seeds.",
                        "No DDR controller, DMA engine, coherence, power measurement, or integrated accelerator cache is modeled."],
    }


class DomainCache:
    """Two-set two-way event model matching rtl/labs/domain_cache.v."""

    def __init__(self, isolated: bool):
        self.isolated = isolated
        self.tags: list[list[tuple[int, int] | None]] = [[None, None], [None, None]]
        self.replacement = [0, 0]
        self.cycles = self.misses = self.reads = 0

    def access(self, line: int, domain: int) -> int:
        if domain not in (0, 1) or line < 0:
            raise ValueError("domain must be 0/1 and line must be nonnegative")
        set_index = line % 2
        allowed = [domain] if self.isolated else [0, 1]
        hit = any(self.tags[set_index][way] is not None and self.tags[set_index][way][0] == line
                  and (not self.isolated or self.tags[set_index][way][1] == domain) for way in allowed)
        latency = 1 if hit else 1 + MEMORY_LATENCY
        if not hit:
            self.misses += 1
            self.reads += 1
            if self.isolated:
                way = domain
            else:
                invalid = [way for way in allowed if self.tags[set_index][way] is None]
                way = invalid[0] if invalid else self.replacement[set_index]
                self.replacement[set_index] = 1 - way
            self.tags[set_index][way] = (line, domain)
        self.cycles += latency
        return latency


def _security_trial(secret: int, isolated: bool, rng: random.Random) -> dict:
    cache = DomainCache(isolated)
    # Prime a candidate in each set. In shared mode a second fill populates both ways.
    for set_index in (0, 1):
        cache.access(set_index, 0)
        if not isolated:
            cache.access(2 + set_index, 0)
    # Secret selects a set, not an address readable by the observer.
    cache.access(8 + secret, 1)
    observed = [cache.access(set_index, 0) for set_index in (0, 1)]
    if observed[0] == observed[1]:
        guess = rng.randrange(2)
    else:
        guess = int(observed[1] > observed[0])
    return {"correct": guess == secret, "cycles": cache.cycles, "misses": cache.misses,
            "memory_transactions": cache.reads, "observed_cycles": observed}


def run_security_lab(seed: int = 7, trials: int = 256) -> dict:
    if trials < 2 or trials % 2:
        raise ValueError("trials must be a positive even number >= 2")
    secrets = [0, 1] * (trials // 2)
    random.Random(seed).shuffle(secrets)
    report = {}
    for isolated, name in ((False, "shared"), (True, "isolated")):
        rng = random.Random(seed + 271)
        results = [_security_trial(secret, isolated, rng) for secret in secrets]
        report[name] = {
            "observer_accuracy": sum(row["correct"] for row in results) / trials,
            "chance_accuracy": 0.5, "trials": trials,
            "cycles": sum(row["cycles"] for row in results),
            "misses": sum(row["misses"] for row in results),
            "memory_transactions": sum(row["memory_transactions"] for row in results),
            "mean_trial_cycles": sum(row["cycles"] for row in results) / trials,
            "observation_examples": [row["observed_cycles"] for row in results[:8]],
        }
    # A separate equal-length benign observer working set quantifies lost associativity.
    def benign_cycles(isolated: bool) -> int:
        cache = DomainCache(isolated)
        for index in range(64):
            cache.access(2 * (index % 2), 0)
        return cache.cycles
    shared_cost, isolated_cost = benign_cycles(False), benign_cycles(True)
    return {
        "lab": "security", "seed": seed, **report,
        "model": {"sets": 2, "ways": 2, "line_bytes": 4, "hit_cycles": 1,
                  "miss_cycles": 13, "isolation": "one way per domain; tags and replacement state isolated",
                  "threat_model": "Two scheduled requesters, no shared data; observer sees only its own probe latency. Binary secret selects one victim cache set."},
        "summary": {"accuracy_reduction": report["shared"]["observer_accuracy"] - report["isolated"]["observer_accuracy"],
                    "benign_accesses": 64, "shared_benign_cycles": shared_cost,
                    "isolated_benign_cycles": isolated_cost,
                    "isolation_slowdown_on_conflicting_benign_trace": isolated_cost / shared_cost},
        "limitations": ["Controlled binary set-selection example, not cryptographic key extraction.",
                        "Fixed scheduling and constant memory latency exclude arbitration/bandwidth channels.",
                        "Chance-level observations in this experiment do not prove general security.",
                        "Trial totals use each mode's appropriate priming sequence; use the separate equal-length benign trace to compare performance.",
                        "No ML monitor is claimed: this small deterministic experiment does not justify training one."],
    }


def run_all_labs(seed: int = 7) -> dict:
    return {"memory": run_memory_lab(seed), "security": run_security_lab(seed)}
