# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, **do not open a public issue**.

Please report it privately by emailing **security@nexaql.dev** with:
- Description of the vulnerability
- Steps to reproduce
- Potential impact

We will acknowledge receipt within 48 hours and provide a fix timeline.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Security Best Practices

When deploying NexaQL:

- Never commit `nexaql.yaml` with real credentials to a public repo
- Use environment variables (`${ENV_VAR}`) for secrets in config
- In production, use JWT auth mode instead of dev-mode headers
- Keep `ANTHROPIC_API_KEY` in environment variables, not in config files
- Run behind a reverse proxy (nginx, Caddy) with TLS in production
