# Dataset Provenance & Research Notes

**Author:** Tanish Renuka Suragihalli  
**Date:** 2026-11-21  
**Project:** NeuralGrid v1.5  

## 1. Provenance of Synthetic Telecom Data
The cellular telemetry used in NeuralGrid is generated from a deterministic 100-cell synthetic network modelled after Bengaluru urban and peri-urban topologies. Cell capacities range from 300 Mbps to 1200 Mbps with an average network degree of 4–6 neighbours per cell.

- **Base Seed:** `42`
- **Tick Interval:** 5 simulation minutes per tick
- **Mass Balance Invariant:** $\text{demand} = \text{served} + \text{queued} + \text{unserved}$ strictly held at every step.

## 2. Event Intelligence Provenance
- **GDELT DOC 2.0:** Public global news database queried via bounded HTTPX requests. Provides news-mention signals and candidate article URLs.
- **RSS/Atom:** Configured public event feeds parsed via Feedparser.
- **Crawl4AI:** Permitted public-page crawler for Schema.org Event structured data extraction.
- **Epistemic Invariant:** A public news mention is a leading indicator of attention, not a ground-truth measurement of attendance. Attendance figures are either extracted from explicit structured markup, provided via operator assumptions, or preserved as `None` / `UNKNOWN`.

## 3. DoNext 5G RAN ML Context & Cautionary Findings
Inspection of the DoNext repository (`27pepablo/donext-5g-ran-ml`) highlights an important negative result in wireless ML literature: UE-side (user equipment) radio measurements alone do not reliably predict application-layer QoS/latency due to channel fading, scheduler variance, and multi-cell interference.

In NeuralGrid:
- We do not make unsupported claims that radio SNR predicts end-to-end latency.
- Latency is computed using an explicit M/M/1-derived queueing formulation based on cell backlog, backhaul utilisation, and active capacity constraints.
