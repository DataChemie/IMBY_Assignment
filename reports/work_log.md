# FDE Technical Evaluation: Daily Work Log & Engineering Decisions

---

## Overview
This log documents the daily hypotheses, experiments, roadblocks, and architectural pivots undertaken during the 7-day FDE technical evaluation for ImBesideYou Inc.

---

## Day 1 — Problem Formulation, Repository Setup & Streaming Architecture

### Objectives
- Review client problem statement in `README.md` and data specification in `DATA_SCHEMA.md`.
- Set up isolated project environment, virtual environment, and dependency management.
- Address large zip archives without exhausting disk space.

### Hypotheses & Experiments
- *Hypothesis 1*: Extracting all 62 Dataset A session archives (~15 GB compressed, containing thousands of screenshot JPEGs) would consume upwards of 60 GB of disk space, risking disk overflow on the host system (26.7 GB free space).
- *Implementation*: Designed `src/io_utils.py` to stream JSONL events directly from `.zip` archives on the fly using Python's `zipfile` module. Only `events.jsonl`, `manifest.json`, and `gt.jsonl` are decompressed in memory.
- *Benchmark*: Event loading achieved >7,000 events/sec without extracting a single image file to disk.

### Failures & Pivots
- *Encountered Issue*: Default Windows PowerShell encoding caused `UnicodeEncodeError: 'charmap'` when encountering Japanese business terms (`住民税通知確認`, `HR人事給与システム`) in console outputs.
- *Fix*: Standardized UTF-8 reconfiguration across all Python entry points via `sys.stdout.reconfigure(encoding='utf-8')`.

### Generative AI Usage
- Used to construct initial data access skeletons and translate domain-specific Japanese HR/Finance terms.

---

## Day 2 — Exploratory Data Analysis (EDA) & Cross-Dataset Diagnostics

### Objectives
- Profile temporal dynamics, application usage distributions, window titles, and URL routes across Dataset A and Dataset B.
- Identify the structural differences between training data (A) and target production data (B).

### Hypotheses & Key Findings
- *Hypothesis 2*: Baseline scripts assumed Dataset B used the same ports (`5122`, `5123`, `5124`) and browser (Chrome) as Dataset A.
- *Empirical Discovery*:
  - Dataset A is dominated by **Google Chrome** (73.6%) on ports `5122–5124`.
  - Dataset B is dominated by **Microsoft Edge** (64.2%) on ports `5132–5134` and features heavy usage of Word policy documents (`gyomu_itaku_kyuuyo_kitei`, `nyusha_checklist_shinsotsu_batch`, `keiyaku_kaijo_tetsuzuki`) and Excel workbooks (`expense_calc`, `budget_analysis`).
  - Web route analysis revealed that Dataset B workers spend overwhelming time on `#/payroll-items` (3,634 events), `#/leave-applications` (1,972 events), `#/onboarding` (1,646 events), and `#/social-insurance` (1,218 events).

### Failed Approaches
- *Attempted*: Training a supervised 15-class classifier on Dataset A process codes (A through O) to classify Dataset B events directly.
- *Reason for Failure*: Cross-domain transfer failure. Because Dataset B features Edge rather than Chrome and connects to ports `5132-5134`, the classifier misclassified new-contract operations and policy checks into arbitrary Dataset A labels.
- *Pivot*: Adopted a **two-tier architecture**: domain-agnostic boundary change-point detection first, followed by semantic clustering and consistent labeling.

---

## Day 3 — Boundary Detection & Ground Truth Alignment on Dataset A

### Objectives
- Analyze the physical triggers that mark business process boundaries in Dataset A ground truth (`gt.jsonl`).
- Calibrate inter-event idle thresholds and minimum execution durations.

### Experiments & Metrics
- Analyzed 790 ground-truth boundaries across 25 Dataset A sessions:
  - `app_switch` (53.4%) and `browser_navigation` (19.6%) accounted for **73.0%** of all boundary onsets.
  - Median inter-event pause at boundaries was 0.5s (mean 2.72s).
  - Ground-truth process durations had a minimum of ~16.8s and a median of 24s to 69s.
- Tested boundary change-point logic against Dataset A GT:
  - Baseline recall: 58.7% GT recall.
  - Refined boundary recall: **69.1% GT recall** with an average boundary error of 35.76s across 10 held-out sessions.

---

## Day 4 — Step 1 Execution: Work Recovery on Dataset B (`segments.jsonl`)

### Objectives
- Run `TaskBoundarySegmenter` across all 15 Dataset B sessions.
- Implement post-processing filters to eliminate micro-toggles and noise bursts.

### Iterations & Improvements
- *Problem*: Initial segmentation produced 319 segments, many of which were 2–4 second blips caused by workers momentarily checking an Excel file or Teams notification before returning to the same portal form.
- *Solution*: Added **Interruption Smoothing**: if a short toggle (< 8s) is sandwiched between identical process contexts, the interruption is absorbed into the primary process.
- *Result*: Generated **222 high-coherence segments** across the 15 sessions (average 14.8 segments/session), with median durations of 33.5s to 46.0s matching empirical human operation logs.
- Generated mandatory deliverable: [`outputs/segments.jsonl`](outputs/segments.jsonl).

---

## Day 5 — Step 2 Execution: Process Mining & Automation ROI Prioritization

### Objectives
- Quantify time consumption, frequency, and variant complexity for all 13 discovered back-office workflows.
- Formulate a formal ROI prioritization matrix.

### Decisions & Discoveries
- Process Mining revealed that **HR Payroll & Deduction Processing (`hr_payroll_deduction_processing` / 給与備考・控除整備)** consumes **3,227 seconds (32.6% of total employee logged time)** across 13 of the 15 sessions.
- Process #2 (`hr_onboarding_verification`) consumed 1,678s (17.0%).
- Process #3 (`hr_maternity_childcare_leave_review`) consumed 1,685s (17.0%).
- *Decision*: Prioritize `hr_payroll_deduction_processing` for Step 3 prototyping due to its massive time concentration, high arithmetic determinism (90%), and low implementation complexity.

---

## Day 6 — Step 3 Execution: Production Automation Prototype Development

### Objectives
- Engineer a working automation tool targeting the #1 candidate.
- Ensure testability, determinism, and robust exception handling.

### Implementation Details
- Built `PayrollAutomationEngine` in [`automation/prototype.py`](automation/prototype.py):
  - Ingests batch employee adjustment records.
  - Automatically calculates health insurance (5.03%), employees' pension (9.15%), and employment insurance (0.6%).
  - Enforces statutory commute allowance ceilings (150,000 JPY cap).
  - Flags exceptions for human review (Article 36 overtime > 45h, large retroactive adjustments > 50,000 JPY).
  - Emits pre-formatted dispatch payloads for `http://127.0.0.1:5132/#/payroll-items`.
- Built automated test suite in [`scripts/test_prototype.py`](scripts/test_prototype.py): 100% test pass rate with full financial audit verification.

---

## Day 7 — Packaging, Verification & Final Report Writing

### Objectives
- Assemble final executive proposal [`reports/final_report.md`](reports/final_report.md).
- Create unified CLI runner [`run.py`](run.py) and end-to-end pipeline script [`scripts/run_pipeline.py`](scripts/run_pipeline.py).
- Verify Git commit history and package all deliverables.

---

## Summary of 7-Day Time Allocation Rationale

| Day | Focus Area | Share | Rationale |
|:---:|:---|:---:|:---|
| **1** | Architecture, Streaming I/O & Environment | 15% | Mitigated disk overflow risk (26 GB disk vs 60 GB uncompressed zips); ensured 0-crash streaming foundation. |
| **2** | Exploratory Data Analysis & Port Diagnostics | 15% | Uncovered critical port/browser shifts in Dataset B, preventing a flawed supervised model. |
| **3** | Ground Truth Calibration on Dataset A | 15% | Grounded segmentation rules in empirical boundary onset statistics (73% app switches/navigations). |
| **4** | Step 1: Work Recovery & Segmentation | 15% | Generated stable `segments.jsonl` with interruption absorption. |
| **5** | Step 2: Process Mining & ROI Prioritization | 15% | Quantitative ranking ensured prototype targets true 32.6% time sink rather than low-impact tasks. |
| **6** | Step 3: Automation Prototype & Testing | 15% | Engineered deterministic, testable prototype with explicit risk handling. |
| **7** | Reporting, Git Packaging & Verification | 10% | Finalized documentation, work log, and verifiable CLI commands. |
