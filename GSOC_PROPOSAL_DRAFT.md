# Google Summer of Code 2026 Proposal

**Project Title:** OpenROAD-MCP Docker Deployment and Cross-Platform Support with Production-Ready Testing and Quality Assurance
**Organization:** The OpenROAD Project
**Mentors:** Jack Luar, Vitor Bandeira, Chaitanya G

---

## 1. Personal Information

*   **Name:** Armaan Bawa
*   **Email:** bawaarmaan2005@gmail.com
*   **GitHub Username:** [@ArmaanBawa](https://github.com/ArmaanBawa)
*   **Discord Username:** [Your Discord Handle]
*   **Time Zone:** IST (UTC +5:30)
*   **University:** NSUT (Netaji Subhas University of Technology)
*   **Availability:** Ready to commit 30-40 hours per week (No overlapping internships or coursework during the coding period).

---

## 2. Executive Summary (Abstract)

The OpenROAD Model Context Protocol (MCP) server is a critical bridge allowing AI assistants—like Claude Code and Gemini—to interact with complex Electronic Design Automation (EDA) and OpenROAD workflows through natural language. However, as the project matures towards its stable v1.0 release, ensuring immediate accessibility via containerization and rock-solid reliability across operating systems is paramount.

Currently, the setup process involves manual local installation, and the existing automated tests, while functional, lack deep integration checks against real workflows, load/stress validations, and memory leak detection.

This proposal outlines a comprehensive infrastructure engineering roadmap to deliver **production-ready Docker images**, **automated GHCR publishing**, **cross-platform CI/CD validation (Ubuntu, macOS, Windows WSL2)**, and an **advanced quality assurance suite**. This new testing infrastructure will include extensive performance frameworks, historical regression tracking, concurrent session testing (50+ sessions), and integrated memory profiling to ensure the long-term stability of the MCP server.

---

## 3. Pre-GSoC Contributions and Why I am the Ideal Candidate

I am extremely passionate about the intersection of DevOps, System Architecture, and EDA toolchains. I have already begun contributing directly to the core goals of this specific GSoC project, proving my ability to navigate the codebase, understand the intricate requirements, and deliver production-ready code.

### 3.1 Completed Pre-GSoC Work (Merged)

My significant contributions to date include:

1.  **Cross-Platform Setup & CI Validation (Merged via `#883cb5e`, refined in `feature/cross-platform-ci`):**

    - **Ubuntu Setup (`setup-ubuntu.sh`):** Automated installation of essential system dependencies (`python3`, `python3-dev`, `build-essential`, `curl`) with interactive confirmation prompts. Uses `uv` as the Python package manager, eliminating the need for redundant `python3-venv` or `git` dependencies.

    - **macOS Setup (`setup-macos.sh`):** Streamlined Homebrew-based setup that validates Homebrew installation and installs `uv`. Leverages `uv sync` to automatically resolve Python version requirements—removing the need to manually specify Python 3.13+.

    - **GitHub Actions Cross-Platform Workflow (`cross-platform.yml`):** Unified CI validation across **Ubuntu 22.04/24.04** and **macOS** using consistent `uv run pytest` commands. Validates:
      - Interactive PTY behavior and MCP protocol compliance
      - Core unit tests and integration tests
      - Docker smoke testing (ensuring the container image boots and MCP responds correctly)

    - **Documentation (`CROSS_PLATFORM.md`):** Comprehensive platform-specific guide including setup instructions, manual steps, known issues, and testing commands for both platforms.

2.  **Concurrent Session Scalability Foundation:**
    Authored the `test_concurrent_session_scalability` pytest functions (in `tests/performance/test_benchmarks.py`) that validate the multiplexing capabilities of the `OpenROADManager` singleton by launching 25+ simultaneous sessions through `asyncio.gather`.

3.  **WSL2 Development Experience Enhancements (Deferred to Future Work):**
    Implemented passwordless `sudo` pre-flight checks and path translation logic between Windows and Linux. This work is currently deferred as the team focuses on Ubuntu and macOS stability first; WSL2 CI integration is planned as a stretch goal.

### 3.2 Strategic Positioning for GSoC

Because I have already completed significant foundational work in **cross-platform CI setup, automated environment configuration, and baseline performance testing**, I will be able to spend the *entirety of the GSoC coding period* tackling the "hard problems":
- **Advanced integration testing** on real ORFS flows (GCD, AES RTL-to-GDSII pipelines)
- **True 50+ concurrent load scaling** and stress testing under sustained throughput
- **Low-level memory profiling and leak detection** with `tracemalloc`/`memray`
- **Historical performance benchmarking** with automated regression detection
- **Production deployment hardening** (Trivy scanning, GHCR publishing optimizations)

---

## 4. Technical Implementation Strategy & Deliverables

The scope of this Medium (175 hours) project is divided into **three major phases**:
1. **Phase 1 (Complete):** Cross-Platform CI setup & automated environment configuration
2. **Phase 2 (GSoC Focus):** Advanced Integration & Load Testing, Memory Profiling
3. **Phase 3 (GSoC Focus):** Performance Benchmarking, Deployment Hardening, Documentation

---

### 4.1. Completed: Production-Ready Cross-Platform Setup (Pre-GSoC ✅)

**Ubuntu & macOS Automated Setup Scripts:**
*   **`setup-ubuntu.sh`:** Installs minimal system dependencies (Python 3 development tools, build essentials, curl) and bootstraps `uv` package manager. Interactive confirmation prevents accidental installations.
*   **`setup-macos.sh`:** Validates Homebrew, installs `uv`, and leverages `uv sync` for automatic Python version resolution.
*   **Key Design Decision:** Both scripts delegate Python version management to `uv`, eliminating redundant manual version specification and reducing setup friction.

**GitHub Actions Cross-Platform Workflow:**
*   Unified `uv run pytest` invocation on both Ubuntu and macOS.
*   Docker smoke test validates container image functionality without duplicating unit tests.
*   Comprehensive documentation in `CROSS_PLATFORM.md`.

---

### 4.2. GSoC Phase 1: Advanced Integration Testing & Concurrent Load Validation

**Real ORFS Flow Integration Tests:**
*   **Strategy:** Expand `tests/integration/` to execute complete RTL-to-GDSII pipelines using lightweight designs (GCD, AES).
*   **Implementation:** Write Pytest fixtures leveraging `OpenROADManager` to:
    1. Synthesize RTL via Yosys, capturing and validating STDOUT logs.
    2. Execute floorplanning, placement, and routing steps.
    3. Extract timing reports and verify correctness via `list_report_images`.
*   **Benefit:** Guarantees AI assistants can drive physical design workflows without regressions across API version updates.

**Concurrent Session Load Testing (50+):**
*   **Problem:** The `OpenROADManager` singleton and its `asyncio.Lock` mechanisms may suffer lock contention or File Descriptor exhaustion under simultaneous session creation.
*   **Solution:** Build specialized load-testing infrastructure using `asyncio` + `pytest` workers:
    - Simulate 50 overlapping interactive sessions.
    - Force concurrent commands (`read_liberty`, `report_checks`) through the PTY layer.
    - Validate that `InteractiveExecResult` responses map correctly to initiating session IDs without cross-pollution.
*   **Metrics:** Measure `p99`, `p95`, and mean latency for command acknowledgement. Identify and fix any FD exhaustion or deadlock scenarios.

---

### 4.3. GSoC Phase 2: Memory Profiling & Performance Benchmarking

**Memory Leak Detection in CI:**
*   **Tooling:** Integrate Python's `tracemalloc` (lightweight) or Bloomberg's `memray` (detailed) via pytest fixtures (`@pytest.mark.memory`).
*   **Test Lifecycle:**
    1. Record baseline memory snapshot.
    2. Launch 30 interactive sessions, stream 50MB of text output via PTY, terminate all sessions.
    3. Force garbage collection (`gc.collect()`).
    4. Assert memory delta < 5MB to catch unclosed FDs and zombie processes.

**Performance Benchmarking with Historical Tracking:**
*   **Implementation:** Integrate `pytest-benchmark` to measure:
    - CPU time for MCP response serialization.
    - Token throughput efficiency.
    - PTY buffer accumulation latency.
*   **Historical Dashboard:** Use `github-action-benchmark` to push JSON results to `gh-pages` branch, generating interactive performance graphs. Automatic PR failure if regressions exceed 15%.

---

### 4.4. GSoC Phase 3: Docker Factory Hardening & Deployment

**GHCR Publishing Workflow Optimization:**
*   **Strategy:** Enhance `.github/workflows/docker-publish.yml` with Docker Actions cache API (`--cache-from`, `--cache-to`) for faster layer reuse.
*   **Security:** Integrate **Trivy** vulnerability scanning. Block GHCR push if high/critical CVEs detected; alert maintainers.
*   **Smoke-Testing:** Before final tag, run PTY sanity check to validate EDA binaries resolve correctly in `/OpenROAD-flow-scripts` environment.

**Comprehensive Deployment Guides:**
*   Finalize `DOCKER_DEPLOYMENT.md` with Kubernetes/cloud deployment examples.
*   Create WSL2 troubleshooting matrix for Windows developers (future work if time permits).
*   Document performance optimization recommendations for production deployments.

### 4.5. Future Work / Stretch Goals (If Time Permits)

**Windows / WSL2 CI Integration:**
*   Implement `setup-wsl2.ps1` PowerShell script with proper `$GITHUB_WORKSPACE` to WSL path translation.
*   Add Windows-latest GitHub Actions job (currently deferred due to WSL2-specific complexity).
*   Comprehensive WSL2 troubleshooting guide and Docker Desktop setup walkthrough.

**Advanced Observability & Alerting:**
*   Integrate structured logging with JSON output for better CI diagnostics.
*   Dashboard for monitoring MCP server health metrics (uptime, latency, error rates) in production.
*   Automated alerts for performance regressions and memory anomalies.

---

## 5. Timeline & Milestones (12 Weeks)

*This timeline is aligned with the required Medium (175 hours) GSoC 2026 format, calculating to ~14.5 hours/week core, with flexibility to dedicate additional effort on high-impact deliverables. Estimated story points per week are shown below.*

---

### Pre-GSoC & Community Bonding Period (May)
**Story Points: 8 points**

*   Finalize cross-platform PR (`feature/cross-platform-ci`) and merge to `main` for stable baseline.
*   Coordinate with Mentors via Discord on which specific ORFS macro designs (GCD, AES) are lightweight for CI integration without exceeding GitHub Actions time limits.
*   Draft architecture for historical benchmarking dashboard and identify `pytest-benchmark` integration points.
*   Set up local memory profiling test environment with `tracemalloc` and `memray`.

---

### Phase 1: Advanced Integration & Load Testing (June)
**Weeks 1-4 | Story Points: 32 points**

| Week | Deliverable | Story Points | Notes |
|------|-------------|--------------|-------|
| 1 | Expand `tests/integration/` with GCD RTL-to-GDSII fixture; implement Pytest parameterization for AES design | 8 | Fixture design, STDOUT log parsing for synthesis validation |
| 2 | Implement full validation logic for floorplan, place, route steps; add `list_report_images` verification | 8 | Handle OpenROAD output variability, build error detection logic |
| 3 | Refactor `manager.py` locking mechanisms; build 50+ concurrent session stress test infrastructure | 8 | Identify lock contention points, design stress test harness |
| 4 | Execute stress tests on PTY buffering; measure `CircularBuffer` limits; document findings and fixes | 8 | Identify FD exhaustion thresholds, concurrency edge cases |

---

### Phase 2: Memory Profiling & Performance Benchmarking (July)
**Weeks 5-8 | Story Points: 32 points**

| Week | Deliverable | Story Points | Notes |
|------|-------------|--------------|-------|
| 5 | Integrate `tracemalloc` into test suite; write `@pytest.mark.memory` decorator and baseline fixtures | 8 | Establish memory baseline, identify profiling thresholds |
| 6 | Build 30-session memory stress test; validate <5MB delta after cleanup; document zombie process detection | 8 | Execute sustained session lifecycle tests |
| 6.5 | **Midterm Evaluations** | — | Project checkpoint with mentors |
| 7 | Introduce `pytest-benchmark` and instrument MCP response serialization, token throughput, buffer latency | 8 | Attach benchmarks to critical code paths |
| 8 | Set up `github-action-benchmark` integration; generate initial performance baseline on `gh-pages` | 8 | Configure automated performance tracking dashboard |

---

### Phase 3: Deployment Hardening & Documentation (August)
**Weeks 9-12 | Story Points: 28 points**

| Week | Deliverable | Story Points | Notes |
|------|-------------|--------------|-------|
| 9 | Enhance `docker-publish.yml` with Docker layer caching API (`--cache-from`, `--cache-to`) | 7 | Reduce CI build times, improve Docker efficiency |
| 10 | Integrate Trivy vulnerability scanning; implement smoke-test phase in Docker CI; ensure GHCR reliability | 7 | Security hardening, GHCR push gate validation |
| 11 | Write `DOCKER_DEPLOYMENT.md` with Kubernetes/cloud examples; finalize `CROSS_PLATFORM.md` troubleshooting matrix | 7 | Comprehensive deployment and debugging guides |
| 12 | Final regression testing, flaky test fixes, PR review & merge, GSoC report submission | 7 | Quality assurance and documentation polish |

**Total Estimated Story Points: 100 points (175 hours ÷ 1.75 hours/point)**

---

## 6. Extensions & Future Work (If Time Permits)

If the above deliverables are completed ahead of schedule, I will pursue the following extensions to maximize long-term impact:

### 6.1. Windows / WSL2 CI Integration (Stretch Goal)
*   Implement `setup-wsl2.ps1` PowerShell script with robust path translation.
*   Add Windows-latest GitHub Actions job with proper WSL2 environment validation.
*   Create WSL2 troubleshooting guide and Docker Desktop setup walkthrough.
*   **Estimated Effort:** 2-3 weeks | **Impact:** Enable Windows developers seamless MCP server setup.

### 6.2. Advanced Observability & Monitoring
*   Structured JSON logging for CI diagnostics and runtime debugging.
*   Production monitoring dashboard for uptime, latency, error rates.
*   Automated alerting for memory anomalies and performance regressions.
*   **Estimated Effort:** 1-2 weeks | **Impact:** Improve production reliability visibility.

### 6.3. ML-Based Optimization & Predictive Analysis
*   Integrate historical benchmark data to predict performance regressions before they reach production.
*   Train lightweight ML models to auto-detect memory leak patterns in CI logs.
*   Automated recommendation system for performance tuning based on workload patterns.
*   **Estimated Effort:** 2-3 weeks | **Impact:** Shift from reactive to proactive issue detection.

### 6.4. Web-Based Observability UI
*   Build a lightweight React/Vue dashboard visualizing real-time MCP server metrics.
*   Interactive performance timeline and memory profiling explorer.
*   One-click environment diagnostics and self-healing suggestions.
*   **Estimated Effort:** 2-3 weeks | **Impact:** Improve user experience for production monitoring.

### 6.5. Advanced Integration Testing Suite Expansion
*   Add tests for large-scale designs (DLX, Ariane RISC-V cores) with performance assertions.
*   Implement multi-session orchestration tests (e.g., parallel GCD and AES flows).
*   Cross-version compatibility testing (backward/forward API compatibility).
*   **Estimated Effort:** 1-2 weeks | **Impact:** Comprehensive design coverage and API stability guarantees.

---

## 7. Summary of Changes from Pre-GSoC Work

The following table summarizes what has been **completed before GSoC** versus what will be **delivered during GSoC**:

| Component | Status | Details |
|-----------|--------|---------|
| **Cross-Platform Setup Scripts** | ✅ Complete | Ubuntu, macOS automated setup with `uv` bootstrapping |
| **GitHub Actions Workflows** | ✅ Complete | Unified Ubuntu/macOS CI with `uv run pytest` |
| **CROSS_PLATFORM.md Documentation** | ✅ Complete | Platform-specific guides and troubleshooting |
| **Advanced Integration Tests (ORFS)** | 📋 GSoC Phase 1 | Real RTL-to-GDSII pipelines with validation |
| **50+ Concurrent Load Testing** | 📋 GSoC Phase 1 | Stress testing with latency and lock contention metrics |
| **Memory Profiling (`tracemalloc`/`memray`)** | 📋 GSoC Phase 2 | Leak detection with <5MB delta validation |
| **Performance Benchmarking Dashboard** | 📋 GSoC Phase 2 | Historical tracking with `github-action-benchmark` |
| **Docker GHCR Security (Trivy)** | 📋 GSoC Phase 3 | Vulnerability scanning and smoke testing |
| **Deployment Guides (Kubernetes)** | 📋 GSoC Phase 3 | Enterprise deployment documentation |
| **Windows/WSL2 CI Integration** | 🔮 Stretch Goal | Deferred to "if time permits" section |

---

## 8. AI Tool Disclosure & Initial Screening Task

### 8.1. AI Tool Disclosure
In accordance with the **OpenROAD Initiative GSoC26 Engagement and AI Policy**, I hereby disclose the use of AI tools during the preparation of this proposal:
*   **AI Tool Used:** Antigravity (powered by Gemini)
*   **Purpose:** Assisting with project research, local environment setup (specifically for the initial screening task), technical formatting, and drafting technical strategy sections.
*   **Human Verification:** Every technical claim, architectural decision, and implementation milestone listed in this proposal has been rigorously verified by me against the `OpenROAD-MCP` codebase and OpenROAD documentation. No generative-AI based explanations for general EDA concepts have been included; all technical logic reflects my personal understanding and prior contributions to the project.
*   **PRs:** PRs are raised by me. If I face any issue, then I take help of AI tools like Antigravity (powered by Gemini) to resolve it. 
*   **Documentation:** Documentation is written by me and to improve its quality like grammar, spelling, and clarity, I take help of AI tools like Claude.


### 8.2. Initial Screening Task Completion
I have successfully completed the required initial screening task:
1.  **Installation:** Installed the OpenROAD flow and ORFS environment using Docker (`openroad/orfs:latest`) to ensure a reproducible and platform-independent verification environment.
2.  **Execution (nangate45/gcd):** Successfully ran the Greatest Common Divisor (GCD) example design through the full RTL-to-GDS flow.
3.  **Verification:** Validated the generation of all required output directories:
    *   `flow/logs/`: Detailed execution logs for synthesis, floorplanning, placement, and routing.
    *   `flow/reports/`: Timing, area, and power reports (e.g., `6_finish.rpt`).
    *   `flow/results/`: Final GDSII and database files.

*Evidence of completion (screenshots of directory structures) is attached to the final submission PDF.*

---

## 9. Commitments and Post-GSoC Involvement

I confirm that I will have full availability during the Coding Period. I am not undertaking any major academic loads or overlapping internships during this time. 

My involvement with The OpenROAD Project will persist long after GSoC 2026 formally concludes. I envision myself actively maintaining the CI/CD pipelines I build and subsequently migrating towards Phase 2 of the `ROADMAP.md`, specifically building Web-based interfaces and exploring Machine Learning optimizations for the server API logic.

Thank you for your time and consideration!
