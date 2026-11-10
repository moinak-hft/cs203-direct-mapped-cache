# Pinned reference CPU

PicoRV32 is used as a compact RV32IM controller so the original accelerator and
firmware can be verified together. The CPU is upstream work, not an original
NeuroTile processor design.

- Repository: https://github.com/YosysHQ/picorv32
- Commit: `ef203c2b0a3fb793280f5114941416c425c5b461`
- `picorv32.v` SHA256:
  `0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622`
- License: ISC, preserved in `COPYING` and the source header.
- Upstream files are included unmodified; upstream is archived.

The SoC enables multiply/divide and configures RV32IM without interrupts or
compressed instructions. Generated firmware uses `-march=rv32im -mabi=ilp32`.
