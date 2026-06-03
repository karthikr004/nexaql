# Contributing to NexaQL

Thank you for your interest in contributing! Here's how to get involved.

## Quick Start

```bash
git clone https://github.com/karthikr004/nexaql
cd nexaql
pip install -e ".[dev]"
cd frontend && npm install && cd ..
nexaql init
nexaql serve --reload
```

## Development Workflow

1. **Fork** the repo and create a branch from `main`
2. Make your changes
3. Add/update tests if applicable
4. Run checks: `pytest tests/ && ruff check src/`
5. Open a **Pull Request** against `main`

All PRs require review before merging.

## Code Style

- Python: formatted with `ruff` (line-length 120)
- TypeScript/React: Tailwind CSS, functional components
- No hardcoded secrets, credentials, or internal URLs

## What to Contribute

- Bug fixes
- New database adapters (MySQL, Snowflake, etc.)
- Ontology examples for different domains
- Documentation improvements
- Test coverage

## What NOT to Submit

- Changes to security/auth without discussion first
- Large architectural changes without an issue/discussion
- Code containing secrets, credentials, or API keys

## Reporting Security Issues

Do **not** open a public issue for security vulnerabilities. Email security@nexaql.dev instead.

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
