"""Hand-computed timing cases, held-out experiments, and RTL equivalence."""
import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'python'))

from neurotile.labs import (
    DomainCache, run_all_labs, run_memory_lab, run_security_lab,
    simulate_cache, simulate_scratchpad, trace_features, train_prefetch_tree,
)


def test_timing_and_prefetch_overlap():
    assert simulate_cache([], "off")["cycles"] == 0
    assert simulate_cache([10], "off")["cycles"] == 21
    no_prefetch = simulate_cache([10, 11], "off")
    prefetched = simulate_cache([10, 11], "next_line")
    assert no_prefetch["cycles"] == 42
    # First demand=21; following demand waits four cycles, then lookup+compute=9.
    assert prefetched["cycles"] == 34
    assert prefetched["demand_reads"] == 1
    assert prefetched["useful_prefetches"] == 1
    # The final unused request remains charged as memory traffic.
    assert prefetched["memory_transactions"] == 3
    assert simulate_cache([10, 10, 10], "off")["cycles"] == 39


def test_conflicts_and_scratchpad_load_cost():
    trace = [0, 16, 0, 16]
    assert simulate_cache(trace, "off")["cycles"] == 84
    scratchpad = simulate_scratchpad(trace)
    assert scratchpad["cycles"] == 60
    assert scratchpad["memory_transactions"] == 2
    assert simulate_scratchpad([0, 1, 2], capacity=2)["memory_transactions"] == 3
    with unittest.TestCase().assertRaises(ValueError):
        simulate_scratchpad([0], capacity=0)


def test_feature_history_and_window_causality():
    assert trace_features(list(range(32))) == [255, 255, 0, 1]
    assert trace_features([4] * 32) == [0, 255, 247, 0]
    tree, _ = train_prefetch_tree()
    first = list(range(32))
    left = simulate_cache(first + [2000] * 32, "learned", tree=tree)
    right = simulate_cache(first + list(range(3000, 3032)), "learned", tree=tree)
    assert left["decisions"][0] == right["decisions"][0]
    assert left["decisions"][0]["policy"] == "next_line"


def test_held_out_report_and_real_baseline_comparison():
    report = run_memory_lab()
    assert report["training"]["rows"] > 100
    train_ids = set(report["training"]["trace_ids"])
    assert not train_ids.intersection(row["id"] for row in report["workloads"])
    for policy in report["summary"]:
        for metric in ("cycles", "memory_transactions"):
            assert report["summary"][policy][metric] == sum(
                row["results"][policy][metric] for row in report["workloads"])
    # Reproducible measured result, including the stronger fixed-stride baseline.
    assert report["summary"]["learned"]["cycles"] < report["summary"]["off"]["cycles"]
    assert report["summary"]["stride"]["cycles"] < report["summary"]["learned"]["cycles"]
    assert json.loads(json.dumps(report))["lab"] == "memory"


def test_domain_state_and_same_address_separation():
    cache = DomainCache(True)
    assert cache.access(0, 0) == 13
    for line in range(2, 32, 2):
        cache.access(line, 1)
        assert cache.access(0, 0) == 1
    assert cache.access(0, 1) == 13  # cannot hit the other domain's tag
    assert cache.access(0, 1) == 1
    assert cache.access(0, 0) == 1
    shared = DomainCache(False)
    assert shared.access(0, 0) == 13
    assert shared.access(0, 1) == 1


def test_controlled_security_experiment_and_capacity_cost():
    report = run_security_lab()
    assert report["shared"]["observer_accuracy"] == 1.0
    assert 0.35 < report["isolated"]["observer_accuracy"] < 0.65
    assert all(row == [1, 1] for row in report["isolated"]["observation_examples"])
    assert report["summary"]["shared_benign_cycles"] == 88
    assert report["summary"]["isolated_benign_cycles"] == 832
    with unittest.TestCase().assertRaises(ValueError):
        run_security_lab(trials=3)
    assert set(json.loads(json.dumps(run_all_labs()))) == {"memory", "security"}


def test_rtl_cache_and_learned_selector_equivalence():
    # Root's helper handles native tools and WSL; skip only when neither exists.
    from tools.common import ROOT, run_tool, tool_available
    if not tool_available("iverilog") or not tool_available("vvp"):
        raise unittest.SkipTest("Icarus Verilog is not installed")
    scratch = ROOT / "work"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="labs-test-", dir=scratch) as temporary:
        _rtl_equivalence(Path(temporary), ROOT, run_tool)


def _rtl_equivalence(tmp_path, ROOT, run_tool):
    tree, _ = train_prefetch_tree(7)
    vectors = tmp_path / "selector_vectors.hex"
    with vectors.open("w", encoding="ascii") as stream:
        for unit in range(256):
            for dominant in range(256):
                # Vary the remaining considered features as well.
                reuse, stride = (unit * 7 + dominant * 3) % 256, (dominant * 11) % 256
                features = [unit, dominant, reuse, stride]
                packed = (unit << 26) | (dominant << 18) | (reuse << 10) | (stride << 2) | tree.predict(features)
                stream.write(f"{packed:09x}\n")
    image = tmp_path / "labs.vvp"
    compiled = run_tool("iverilog", ["-g2012", "-s", "tb_labs", "-o", str(image),
        str(ROOT / "rtl/labs/adaptive_selector.v"), str(ROOT / "rtl/labs/domain_cache.v"),
        str(ROOT / "sim/tb_labs.sv")], cwd=ROOT)
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr
    simulated = run_tool("vvp", [str(image), f"+vectors={vectors.relative_to(ROOT).as_posix()}"], cwd=ROOT)
    assert simulated.returncode == 0, simulated.stdout + simulated.stderr
    assert "LABS_RTL_PASS" in simulated.stdout
    assert "selector_checks=65543" in simulated.stdout


# Keep the numerical checks easy to read while supporting stdlib unittest discovery.
class LabsTests(unittest.TestCase):
    test_timing_and_prefetch_overlap = staticmethod(test_timing_and_prefetch_overlap)
    test_conflicts_and_scratchpad_load_cost = staticmethod(test_conflicts_and_scratchpad_load_cost)
    test_feature_history_and_window_causality = staticmethod(test_feature_history_and_window_causality)
    test_held_out_report_and_real_baseline_comparison = staticmethod(test_held_out_report_and_real_baseline_comparison)
    test_domain_state_and_same_address_separation = staticmethod(test_domain_state_and_same_address_separation)
    test_controlled_security_experiment_and_capacity_cost = staticmethod(test_controlled_security_experiment_and_capacity_cost)
    test_rtl_cache_and_learned_selector_equivalence = staticmethod(test_rtl_cache_and_learned_selector_equivalence)


if __name__ == "__main__":
    unittest.main()
