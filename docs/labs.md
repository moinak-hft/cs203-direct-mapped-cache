# Architecture labs

These two runnable experiments are independent of the NeuroTile AI SoC. They
do not claim the accelerator has a cache, that a CPU executes these traces, or
that Python timing estimates are FPGA measurements.

## Run and inspect

From the repository root, `python tools/labs.py` regenerates both reports.
The following APIs return JSON-serializable dictionaries and need only Python's
standard library (add the local `python/` source directory to the import path):

```python
import sys
sys.path.insert(0, "python")
from neurotile.labs import run_memory_lab, run_security_lab, run_all_labs

memory = run_memory_lab(seed=7)
security = run_security_lab(seed=7, trials=256)
both = run_all_labs(seed=7)
```

Run the numerical checks and self-checking RTL bench from the repository root:

```text
python -m unittest discover -s tests -p test_labs.py -v
```

The tests use `tools.common` to locate native Icarus tools or their WSL versions.
The RTL test is skipped, with a visible reason, when Icarus is absent. It compiles
`rtl/labs/adaptive_selector.v`, `rtl/labs/domain_cache.v`, and `sim/tb_labs.sv`.
The bench also works independently without generated selector vectors.

## Memory experiment: cache, scratchpad, and trained policy selection

Seven held-out 384-access traces exercise forward streams, strides, reverse
streams, a reused hot set, random accesses, phase changes, and four conflicting
lines. Addresses are **line indices**. The direct-mapped cache has 16 lines of
16 bytes each, or 256 bytes. The scratchpad has the same line capacity.

The reported cycle model is explicit:

* A demand lookup costs one cycle. Its following computation costs eight cycles.
* A memory read takes twelve cycles. There is one pending prefetch slot and one
  memory read port. Prefetches overlap computation.
* A demand miss waits for any outstanding read. If that read supplies the needed
  line, no duplicate demand read is issued. Otherwise the demand starts its own
  twelve-cycle memory read.
* A prefetch completion installs its line and may evict another line. A demand
  can hit the cache while an unrelated prefetch is in flight.
* Every issued read is charged as traffic, including a final unused prefetch.
  The run ends after the final demand's compute gap; it does not wait solely to
  drain a useless final prefetch.

For example, two cold consecutive demands cost 42 cycles with prefetching off.
Next-line prefetch reduces this to 34: the second demand waits four remaining
memory cycles, then performs its lookup and compute. It issues three reads,
because the final speculative read is included. Reduced cycles can therefore
come with increased traffic.

`off`, `next_line`, and `stride` are measured on the same full traces. The stride
predictor requires two matching successive deltas before requesting the next
line. `rule` and `learned` select one of these policies every 32 demands, using
only the **previous** 32 demands. They begin with prefetching off.

The scratchpad implementation explicitly preloads a tile containing at most 16
distinct lines. A tile extends until adding another demand would exceed that
capacity; the next tile starts empty. Every tile line copy costs twelve cycles,
without DMA overlap. Its address schedule is known in advance, as it could be
for a regular software kernel. This assumption does not apply to unknown pointer
chains. On the conflicting four-line trace, the direct-mapped cache repeatedly
misses while the scratchpad loads the four lines once.

### What is actually trained

A pure-Python CART classifier uses Gini impurity and depth at most three. Its
four candidate integer features, scaled to 0–255, are unit-delta frequency,
dominant-delta frequency, repeated-address fraction, and absolute dominant
stride. Redundant leaf splits are pruned.

Training consists of 48 complete synthetic traces, eight instances from each of
six families. The offline label for a sample is the lowest-cycle fixed policy
on the next cold-cache window. Ties prefer off, then next-line. The inference
features come from the preceding window. Full adaptive evaluation preserves
cache and predictor state between windows, so label accuracy and total-cycle
performance are different measurements.

The test split holds out entire traces, seeds, and trace lengths. Six families
overlap training; the conflict family is absent from training. This demonstrates
synthetic trace generalization, not deployment on arbitrary programs. Training
and held-out classification accuracy, tree structure, trace IDs, and full policy
measurements are included in the report.

The default learned tree simplifies to:

```text
if unit_delta > 0:             next_line
else if dominant_delta <= 16:  off
else if dominant_delta <= 49:  next_line
else:                         stride
```

`adaptive_selector.v` implements precisely this seed-7 trained tree. The test
computes expected outputs from the independently trained Python tree for all
65,536 combinations of its two selected features, while also varying the two
unused candidate features. The RTL is a selector only: feature extraction,
prefetch queues, and the timing simulator execute in Python. Retraining with
another seed does not rewrite the checked-in RTL.

Default seed-7 aggregate results over 2,688 demand accesses:

| Policy | Modeled cycles | Memory reads | Speedup versus off |
|---|---:|---:|---:|
| Off | 50,736 | 2,212 | 1.000 |
| Next-line | 52,076 | 3,540 | 0.974 |
| Fixed stride | 39,724 | 2,320 | 1.277 |
| Fixed rule selector | 41,072 | 2,339 | 1.235 |
| Trained tree selector | 41,072 | 2,339 | 1.235 |
| Scheduled scratchpad | 46,248 | 1,838 | 1.097 |

The learned selector ties the rule and loses to fixed stride on this collection.
This result is intentionally retained. Training a model does not guarantee an
improvement over a well chosen simple policy. Default held-out classification
accuracy is 73/77 windows (94.805%); that figure is not an application accuracy
or hardware speedup.

## Security experiment: one controlled timing channel

The model has two sets and two ways, with one 32-bit word per line. A hit costs
one modeled cycle; a miss costs thirteen. In shared mode, a per-set round-robin
replacement bit selects victims after empty ways have been filled. Either domain
can hit a shared line. In isolated mode, domain 0 owns way 0 and domain 1 owns
way 1. Domain checks apply to hits and allocation; one private way needs no
replacement pointer, so there is no shared replacement state to update.

Each trial resets the cache. The observer primes candidate lines, the victim
accesses a private line in a set selected by a binary secret, and the observer
times its own probes. It guesses which probe was slower; equal timings cause a
seeded random guess. The observer does not inspect victim addresses or tags.
The balanced secret sequence and random guesses are reproducible.

With seed 7 and 256 trials, the shared observer guesses 100% correctly; the
isolated observer guesses 48.046875%, against a 50% chance baseline. Every
isolated observation is `[1, 1]`. These numbers describe this controlled
set-selection experiment, not extraction of cryptographic keys or proof of
general security. Fixed scheduling and fixed memory latency exclude memory
bandwidth and arbitration channels.

The modes need different priming sequences, so their total trial cycles must
not be interpreted as a performance comparison. A separate **identical**
64-access benign trace alternates between two lines in one set. Shared mode
costs 88 modeled cycles; isolation costs 832, a 9.455x slowdown for that
deliberately adverse working set. Partitioning can impose a real capacity cost.

### What the security RTL does

`domain_cache.v` is a synthesizable tiny data/tag cache prototype. Each accepted
request performs an atomic lookup/fill event. On a miss, the harness supplies
the line word through `request_fill_data`. A response appears at the clock edge
that accepts the request, with `response_valid`, hit status, data, and a cost
annotation. `response_cost=13` **does not** mean a thirteen-clock memory
controller exists. There is no backing-memory bus or integration with the SoC.

`ISOLATE` is a compile-time parameter; there is no unsafe live repartitioning.
The bench instantiates both modes, checks the controlled leak, exercises foreign
domain churn, verifies same-address cross-domain misses, checks reset, and tests
returned data. Python tests independently verify the timing and isolation
behaviors. Yosys `proc; opt; check` accepts both standalone modules; this is an
RTL structural check, not place-and-route or a timing closure claim.

No ML security monitor is included: this small deterministic experiment does
not provide a credible dataset or an adversarial detection evaluation. The
trained ML component belongs to the memory policy experiment.

## Research context

The isolation experiment is inspired by the principle of separating cache tags
and replacement metadata discussed in [DAWG, MICRO 2018](https://dspace.mit.edu/entities/publication/15d7aefb-e266-401c-ba9a-b18b4493090c).
It is not an implementation of DAWG or a speculative CPU. The decision to avoid
claiming an ML attack detector follows the evaluation concerns in
[SoK: Can We Really Detect Cache Side-Channel Attacks by Monitoring Performance Counters?, ASIACCS 2024](https://digital.library.adelaide.edu.au/items/37fac8ba-8cae-4f8f-bfb4-bbaae1689215).
