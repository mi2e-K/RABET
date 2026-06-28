# RABET documentation

User-facing and developer-facing documentation for RABET 1.4.0.

| Document | Audience | Description |
| --- | --- | --- |
| [User Guide (English)](USER_GUIDE.md) | End users | End-to-end walkthrough of RABET 1.4.0: annotation, state/point event types, multi-file analysis, bout analysis, transition analysis, visualisation, reliability assessment, project mode, and troubleshooting. |
| [User Guide (Japanese)](USER_GUIDE.ja.md) | End users | Natural Japanese-language guide covering the same RABET 1.4.0 workflows. |
| [CSV format specification](CSV_FORMAT.md) | End users, integrators | Complete specification of the annotation, summary, and interval-summary CSV layouts with a minimal pandas parser. |
| [Reliability assessment reference](reliability/README.md) | Statisticians, reviewers | Notes on the Reliability tab, plus an R script (`compute_agreement.R`) that reproduces RABET's Summary-mode ICC / Pearson / mean-absolute-difference values using `psych::ICC`. |
| [Build instructions (macOS / Linux)](BUILD_MACOS_LINUX.md) | Contributors | Platform-specific notes for building self-contained RABET binaries from source. |

For an at-a-glance overview of the project, installation, and citation,
see the top-level [`README.md`](../README.md).
