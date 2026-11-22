# Roadmap

Priorities, in order. There are no release dates; items move when they are
ready and tested.

1. **Reliable installation.** A fresh install on Windows, macOS and Linux
   should reach a working `aegis doctor` and a first report without
   guesswork. Track every install problem reported in issues and fix the
   cause, not only the documentation.
2. **Citation-verification correctness.** Citation checks are the most
   verifiable thing AEGIS does. Grow `benchmarks/citations/`, fix known
   misses (author parsing first), and keep the rule that timeouts, rate
   limits and other registration agencies are never reported as fabricated.
3. **Parser robustness.** Reference and section extraction across real PDF,
   DOCX and LaTeX layouts, tested with redistributable samples.
4. **Reproducible evaluation.** Before any accuracy or fairness claim, publish
   the dataset, method and results, including failures. AI-text detection and
   ESL calibration stay labelled experimental until then.
5. **Security regression tests.** Every control in
   [docs/SECURITY_MODEL.md](../SECURITY_MODEL.md) has a test; new tools and
   network calls get one too.

Not planned for now: a hosted multi-user service. AEGIS stays local-first.
