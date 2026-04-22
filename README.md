# Direct-Mapped Cache Memory Design (CS-203)

This repository contains the Verilog HDL implementation of a **direct-mapped cache memory system**, developed as part of the **CS-203: Digital Logic Design** course at IIT Ropar.

The project focuses on understanding memory hierarchy concepts, cache addressing, and control logic through a hardware-level implementation.

## 📌 Project Overview

Caches improve processor performance by storing frequently accessed data closer to the CPU.  
This project implements a **direct-mapped cache**, where each block of main memory maps to exactly one cache line.

The design demonstrates:
- Cache hit and miss detection
- Tag comparison and valid-bit based control
- Read and write operations
- Interaction between cache and main memory

## 🛠 Features

- Direct-mapped cache architecture
- Tag comparison for hit/miss detection
- Valid bit based cache line management
- Read and write control logic
- Integration with a simple main memory module
- Fully functional testbench for verification

## 🧱 Architecture Components

- **Cache Memory Array**  
  Stores data blocks along with tag and valid information.

- **Control Logic (FSM-based)**  
  Handles read/write operations, hit/miss decisions, and cache updates.

- **Main Memory Module**  
  Simulates lower-level memory access during cache misses.

## 🧪 Verification

A Verilog testbench is included to validate cache behavior under different scenarios:
- Consecutive reads to the same address (cache hits)
- Accesses to conflicting addresses (cache misses)
- Read-after-write consistency checks

Waveforms were analyzed to verify correctness of data output and hit/miss signals.

## 🧰 Tech Stack

- Verilog HDL
- Digital Logic Design
- FSM-based Control Logic
- Testbench Simulation

## 📚 Learning Outcomes

- Practical understanding of cache memory organization
- Hands-on experience with Verilog-based hardware design
- Insight into memory hierarchy and cache performance trade-offs
- Foundation for advanced cache designs (set-associative, fully associative)

## 👤 Team Member's:
1. Moinak Goswami 2024CSB1225
2. Sarthak Nitin Keshaowar 2024CSB1215
3. Harshit Sahu 2024CSB1203
4. Palak Gulati 2024CSB1137
5. Garima Kamra 2024CSB1115
