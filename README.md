# ImBesideYou FDE Technical Evaluation: Operation Logs to Automation Proposal
**NAME:** Sammriddha Kar 
**University:** IIT Mandi
**Department/Major:** MBA in AI/DS
**Email ID:** mb26016@students.iitmandi.ac.in
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Status](https://img.shields.io/badge/status-complete-brightgreen.svg)]()

> **Mission Statement:**
> *"Use these logs to tell us where automation would have the greatest impact on our operations. And show us something that actually works."*

---

## 1. Executive Summary

This repository delivers an end-to-end, production-oriented solution for the 7-day FDE technical evaluation. By analyzing 63 ground-truth sessions in **Dataset A** (~152,000 events) and 15 unlabeled sessions in **Dataset B** (~20,000 events) from a Japanese corporate environment, we:

1. **Recovered Coherent Units of Work (Step 1)**: Developed a transferable, domain-agnostic boundary detector that identifies task change-points from OS and browser telemetry without overfitting to Dataset A's business labels. Output: [`outputs/segments.jsonl`](outputs/segments.jsonl) (222 validated business process segments).
2. **Analyzed Operational Bottlenecks & Ranked Candidates (Step 2)**: Conducted process mining and variance analysis across all recovered segments. Formulated a multi-factor ROI matrix (`Time Spent × Determinism × Feasibility / Complexity`). Ranked 13 distinct back-office workflows. Identified **HR Payroll & Deduction Processing (`hr_payroll_deduction_processing` / 給与備考・控除整備)** as the #1 automation target (consuming 32.6% of total employee logged time).
3. **Engineered a Production-Grade Automation Engine (Step 3)**: Implemented and validated a deterministic batch automation engine in [`automation/prototype.py`](automation/prototype.py) that automates statutory tax/pension deductions, commute allowances, and web portal submission payloads (`http://127.0.0.1:5132/#/payroll-items`), complete with human-in-the-loop exception handling for Article 36 overtime and large adjustments.

---

## 2. Project Architecture & Directory Structure

```text
ImBesideYouAssignment/
├── config/
│   └── paths.py                 # Centralized configuration & dataset path resolution
├── src/
│   ├── __init__.py
│   ├── io_utils.py              # High-performance streaming zip loader & timestamp normalizer
│   ├── ground_truth.py          # Dataset A ground truth interval extractor & evaluator
│   ├── features.py              # Domain-agnostic transition features & contextual text extraction
│   ├── segmenter.py             # TaskBoundarySegmenter (change-point detection + interruption smoothing)
│   ├── evaluate.py              # Precision, Recall, F1, and Boundary Mean Error evaluator
│   └── process_miner.py         # Process mining engine & multi-factor ROI candidate ranker
├── automation/
│   ├── __init__.py
│   └── prototype.py             # Step 3 Automation Prototype (HR Payroll & Deduction Engine)
├── scripts/
│   ├── preflight_check.py       # Pre-flight environment, disk space, and streaming I/O test
│   ├── run_eda.py               # Comparative EDA across Dataset A and Dataset B
│   ├── analyze_boundaries.py    # Ground truth boundary onset & duration distribution analysis
│   ├── run_eval_a.py            # Automated evaluation runner against Dataset A GT
│   ├── test_prototype.py        # Automated test suite for Step 3 automation prototype
│   └── run_pipeline.py          # Unified end-to-end pipeline runner
├── reports/
│   ├── final_report.md          # Comprehensive final report for executive stakeholders
│   ├── work_log.md              # 7-day chronological engineering work log & thought process
│   ├── eda_summary.json         # Raw statistics from cross-dataset exploratory analysis
│   └── process_mining_roi.json  # Full process mining and ROI candidate ranking table
├── outputs/
│   ├── segments.jsonl           # Deliverable #1: Recovered units of work on Dataset B
│   ├── sample_payroll_input.csv # Realistic test payroll dataset for prototype
│   └── automation_run_summary.json # Execution audit trail of the automation prototype
├── requirements.txt             # Strict pinned dependencies
├── .gitignore                   # Version control ignore rules
├── README.md                    # Project documentation
└── run.py                       # Unified command-line interface
```

---

## 3. Quick Start & Execution Guide

### Prerequisites
- Windows 10/11 (PowerShell)
- Python 3.10+ (tested on Python 3.13)

### Virtual Environment Setup
```powershell
# In C:\Users\User\Documents\ImBesideYouAssignment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Running Commands via Unified CLI (`run.py`)

#### 0. Provide path to your training and test dataset
Add path to your training and test dataset files in .env

#### 1. Run Pre-flight Diagnostic Checks
Validates environment, disk space, dataset access, and streaming I/O speeds:
```powershell
python run.py preflight
```

#### 2. Run Exploratory Data Analysis (EDA)
Inspects active apps, window titles, URLs, and keystroke events across A and B:
```powershell
python run.py eda
```

#### 3. Run Step 1: Work Recovery on Dataset B (`segments.jsonl`)
Generates the mandatory Deliverable 1 in [`outputs/segments.jsonl`](outputs/segments.jsonl):
```powershell
python run.py segment
```

#### 4. Evaluate Segmentation on Dataset A Ground Truth
Evaluates boundary precision, recall, and error against ground-truth labels:
```powershell
python run.py eval-a --sessions 62
```

#### 5. Run Step 2: Process Mining & ROI Candidate Prioritization
Ranks all recovered back-office processes by quantitative ROI score:
```powershell
python run.py mine
```

#### 6. Run Step 3: Automation Prototype
Executes the payroll automation engine with automated test cases:
```powershell
python run.py prototype
```

#### 7. Execute the Entire Pipeline End-to-End
Runs pre-flight, segmentation, evaluation, process mining, and prototype tests sequentially:
```powershell
python run.py all
```

---

## 4. Key Empirical Findings (Dataset A vs Dataset B)

Our exploratory analysis uncovered critical structural differences between the two datasets:

| Metric / Dimension | Dataset A (Training / Validation) | Dataset B (Production Environment) |
|---|---|---|
| **Sessions** | 62 sessions available (~162k events) | 15 sessions (~21k events) |
| **Ground Truth** | Yes (`gt.jsonl`, `gt_manifest.json`) | **None** (Blind evaluation) |
| **Primary Browser** | Google Chrome (73.6% of events) | Microsoft Edge (64.2% of events) |
| **Primary Office Apps** | Notepad (16.5%), MS Word (4.4%) | MS Word (19.6%), MS Excel (5.7%) |
| **Portal Host / Ports** | `http://127.0.0.1:5122`, `5123`, `5124` | `http://127.0.0.1:5132`, `5133`, `5134` |
| **Web Routes** | Balanced HR, Finance, Ops routes | Heavily weighted to `#/payroll-items` (3,634 events), `#/leave-applications` (1,972), `#/onboarding` (1,646) |
| **Boundary Onset** | `app_switch` (53.4%), `browser_navigation` (19.6%) | Route change & app switch trigger 71%+ of transitions |
| **Median Duration** | 24.0s – 68.9s (Min: ~17s) | 33.5s – 46.0s (Min: 4s after filtering) |

---

## 5. Deliverable Summary

1. **Deliverable 1**: [`outputs/segments.jsonl`](outputs/segments.jsonl)
   - 222 coherent segments across all 15 Dataset B sessions.
   - Exact schema: `{"session_id": "...", "start": "...Z", "end": "...Z", "label": "..."}`.
2. **Deliverable 2**: Full Git repository with structured commit history.
3. **Deliverable 3**: Comprehensive Final Report ([`reports/final_report.md`](reports/final_report.md)).
4. **Deliverable 4**: Chronological Work Log ([`reports/work_log.md`](reports/work_log.md)).
