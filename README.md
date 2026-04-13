# Oracle Forge — Data Agent

A context-injection knowledge base for an LLM-powered multi-database analytics agent, built for the [DAB benchmark](https://github.com/DABenchmark).

## How It Works

Every file in `kb/` is a self-contained document designed to be injected directly into an LLM context window. No RAG, no embeddings — documents are loaded by path and pasted as system context before query execution.

Documents are validated with **injection tests**: a fresh LLM session receives only the document, is asked a question it should answer, and must match ≥70% of expected keywords to pass.

## Repository Structure

```markdown
oracle-forge-data-agent/
├── kb/                              # The agent's knowledge base
│   ├── architecture/                # How the agent thinks
│   │   ├── memory.md                  # Three-layer memory system
│   │   ├── conductor_worker_pattern.md # Multi-database routing
│   │   ├── openai_layers.md           # Six-layer context architecture
│   │   ├── autodream_consolidation.md # Weekly session compression
│   │   ├── tool_scoping_philosophy.md # 40+ tight tools > 5 generic
│   │   └── evaluation_harness_schema.md # Trace schema + pass@1
│   ├── domain/                      # DAB dataset knowledge
│   │   ├── databases/               # PostgreSQL, MongoDB, SQLite, DuckDB schemas
│   │   ├── joins/                   # Cross-DB join key transformations
│   │   ├── unstructured/            # Sentiment + text extraction patterns
│   │   └── domain_terms/            # Business glossary (telecom, Yelp, healthcare)
│   ├── correction/                  # Self-learning correction loop
│   │   ├── failure_log.md           # Chronological failures + fixes
│   │   ├── failure_by_category.md   # Failures by DAB's 4 categories
│   │   ├── resolved_patterns.md     # Permanent fixes with confidence scores
│   │   └── regression_prevention.md # Regression test rules
│   ├── evaluation/                  # DAB benchmark reference
│   │   ├── dab_scoring_method.md    # pass@1 definition and calculation
│   │   └── submission_format.md     # PR requirements + AGENT.md template
│   ├── injection_test.py            # Injection test runner (Groq Llama)
│   └── CHANGELOG.md                 # Version history
│
├── planning/                        # Team planning documents
├── requirements.txt                 # Python dependencies
└── setup_groq_tests.sh              # API key setup + test quickstart
```

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure Groq API key (interactive — writes key to .env)
bash setup_groq_tests.sh

# Or add to .env manually (run_injection_tests.py reads this automatically)
echo 'GROQ_API_KEY="your-key-here"' >> .env

# Or export for the current shell session only
export GROQ_API_KEY="your-key-here"
```

## Running Injection Tests

Use `run_injection_tests.py` from the **project root** — it reads `.env` automatically and saves timestamped results to `injection_results/`.

```bash
# Full suite — saves JSON + Markdown to injection_results/
python run_injection_tests.py

# Full suite with LLM answers printed
python run_injection_tests.py --verbose

# Full suite + update kb/INJECTION_TEST_LOG.md
python run_injection_tests.py --update-log

# Check that all document paths resolve (no API call)
python run_injection_tests.py --validate-paths

# Test a single document
python run_injection_tests.py --test-single architecture/memory.md

# Custom results directory
python run_injection_tests.py --results-dir ./my_results
```

**Direct runner** (if you need lower-level control or are calling from a script):

```bash
# Must be run from the project root; pass --kb-path and --api-key explicitly
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY"
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --verbose
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --test-single architecture/memory.md
python kb/injection_test.py --kb-path ./kb --api-key "$GROQ_API_KEY" --validate-paths
```

Results are written to `injection_results/` as `injection_test_YYYY-MM-DD_HH-MM-SS.json` and `.md`.

Current pass rate: **21/21 (100%)** — see `injection_results/`.

## Session Start — Document Load Order

Inject these files at the start of every agent session:

1. `architecture/memory.md`
2. `architecture/conductor_worker_pattern.md`
3. `architecture/openai_layers.md`
4. `correction/failure_log.md`
5. `correction/resolved_patterns.md`

Then load on demand:

- `domain/databases/<db>_schemas.md` for each database type in the query
- `domain/joins/join_key_mappings.md` for any cross-database join
- `domain/domain_terms/business_glossary.md` for telecom / Yelp / healthcare queries

## Adding a KB Document

1. Create the file in the appropriate `kb/` subdirectory
2. Add a test case to `EXPECTED_ANSWERS` in `kb/injection_test.py`
3. Run `python kb/injection_test.py --test-single <path> --verbose`
4. Revise until the test passes, then add a `CHANGELOG.md` entry

## Attribution

- Three-layer memory + autoDream — Claude Code architecture (March 2026)
- Six-layer context — OpenAI data agent writeup (Jan 2026)
- Injection test methodology — Andrej Karpathy
- Domain requirements — UC Berkeley DAB benchmark
