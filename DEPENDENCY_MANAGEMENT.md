# Dependency Management Guide

This document explains how to manage Python dependencies safely and securely for the Legal Research Assistant MCP.

**Last Updated:** 2025-12-12
**Package Manager:** uv (recommended), pip (supported)
**Python Version:** 3.12+

---

## Table of Contents

1. [Overview](#overview)
2. [Dependency Hierarchy](#dependency-hierarchy)
3. [Adding Dependencies](#adding-dependencies)
4. [Updating Dependencies](#updating-dependencies)
5. [Security Scanning](#security-scanning)
6. [Troubleshooting](#troubleshooting)
7. [Best Practices](#best-practices)

---

## Overview

### Project Dependencies

**Production Dependencies** (in `pyproject.toml`)
- FastMCP: MCP server framework
- FastAPI: REST API framework
- Pydantic: Data validation
- httpx: HTTP client with retries
- NetworkX: Graph/network analysis
- ChromaDB: Vector database for semantic search
- Transformers: NLP/ML models
- Other utilities (caching, templating, etc.)

**Development Dependencies** (in `[project.optional-dependencies]`)
- pytest: Testing framework
- ruff: Linting and formatting
- mypy: Type checking

### Dependency Lock File

`uv.lock` - Records exact versions of all transitive dependencies
- Ensures reproducible builds across environments
- Committed to version control
- Should not be manually edited

---

## Dependency Hierarchy

### Direct vs Transitive Dependencies

```
Your Application
├── Direct: fastapi>=0.109.0
│   ├── Transitive: starlette>=0.27.0
│   ├── Transitive: pydantic>=2.0.0
│   └── Transitive: typing-extensions>=4.0.0
├── Direct: httpx>=0.27.0
│   ├── Transitive: certifi>=2024.0.0
│   └── Transitive: h2>=4.0.0
└── Direct: transformers>=4.36.0
    ├── Transitive: huggingface-hub>=0.16.0
    ├── Transitive: numpy>=1.16.0
    └── Transitive: torch>=1.9.0 (large!)
```

### Dependency Size Impact

| Package | Size | Purpose | Necessity |
|---------|------|---------|-----------|
| transformers | ~500MB | NLP models | Required for quote matching |
| torch | ~2GB | ML framework | Required by transformers (CPU) |
| chromadb | ~50MB | Vector DB | Required for semantic search |
| fastapi | ~20MB | Web framework | Required for API |
| httpx | ~2MB | HTTP client | Required for CourtListener API |

**Total size:** ~2.5GB (single architecture, CPU only)

### Why Size Matters

- **Docker image size:** Slower builds, harder to push to registries
- **Container startup:** Takes longer to pull image
- **Memory usage:** Large dependency trees use more RAM
- **Security surface:** More code = more potential vulnerabilities

---

## Adding Dependencies

### Using uv (Recommended)

```bash
# Add production dependency
uv add package-name>=1.0.0

# Add development-only dependency
uv add --dev pytest-cov>=4.0.0

# Add with specific version
uv add "requests>=2.28.0,<3.0.0"

# Add extras
uv add "requests[security]>=2.28.0"
```

### Manual Addition

Edit `pyproject.toml` under `[project] dependencies` or `[project.optional-dependencies] dev`:

```toml
[project]
dependencies = [
    "fastapi>=0.109.0",
    "new-package>=1.0.0",  # Add here
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "new-dev-tool>=2.0.0",  # Add here
]
```

Then sync:
```bash
uv sync --dev
```

### Before Adding a Dependency

1. **Check if it's needed**
   - Is there built-in functionality?
   - Are alternatives lighter weight?
   - Example: Use `json` instead of `simplejson`

2. **Check the size**
   ```bash
   pip download package-name --no-deps --python-version 312
   unzip package_name-*.whl
   du -sh package_name/
   ```

3. **Check security**
   - Known vulnerabilities? `safety check`
   - Actively maintained?
   - Review GitHub issues and PRs

4. **Check if it's production or dev**
   - Production = ships with app (keep minimal)
   - Dev = only used in testing/development (can be heavier)

---

## Updating Dependencies

### Automated Updates (Dependabot)

**Setup:**
- `.github/dependabot.yml` configures automatic updates
- Runs weekly on Monday at 3 AM UTC
- Creates pull requests with updates
- Includes security patches automatically

**How it works:**
```yaml
- package-ecosystem: "pip"
  schedule:
    interval: "weekly"
    day: "monday"
    time: "03:00"
```

### Manual Updates

#### Update All Production Dependencies

```bash
# Check what would update
uv pip compile --upgrade pyproject.toml

# Actually update
uv sync --upgrade
```

#### Update Specific Package

```bash
# Update one package
uv pip compile --upgrade-package httpx pyproject.toml
uv sync
```

#### Controlled Version Updates

```bash
# Update with constraints
uv add "fastapi>=0.110.0,<0.111.0"  # Minor version only
uv add "httpx>=0.28.0"              # Latest (major versions ok)
```

### Review Process for Updates

1. **Read changelog**
   - Check for breaking changes
   - Check for security fixes
   - Check for new requirements

2. **Test locally**
   ```bash
   uv sync --dev
   uv run pytest
   uv run ruff check .
   uv run mypy app/
   ```

3. **Check lock file changes**
   ```bash
   git diff uv.lock | head -50
   # Look for: version bumps, new dependencies, removed dependencies
   ```

4. **Merge if safe**
   ```bash
   git checkout main
   git pull
   git merge dependabot/pip/xxx
   git push
   ```

---

## Security Scanning

### Running Safety Check Locally

```bash
# Install safety
uv add --dev safety

# Check for known vulnerabilities
uv run safety check

# Output format:
# ╒════════════════════════════════════════════════════════════════╕
# │ security scan report                                           │
# ├════════════════════════════════════════════════════════════════┤
# │ package: xxx
# │ vulnerability: CVE-XXXX-XXXXX (High)
# │ affected versions: <1.0.0
# │ installed version: 0.9.5
# │ vulnerability description: ...
# │ remediation: Upgrade to >=1.0.0
# ├════════════════════════════════════════════════════════════════┤
# │ 1 vulnerability found
# └════════════════════════════════════════════════════════════════┘
```

### GitHub Automated Scanning

**Dependabot Security Updates:**
- Automatically detects CVEs in dependencies
- Creates pull requests with fixes
- Runs CI checks automatically

**How to respond:**
1. Dependabot creates PR: "Bump httpx from 0.24.0 to 0.24.1"
2. Review description for CVE details
3. Run local tests: `uv sync && uv run pytest`
4. Merge if tests pass

### Advanced Scanning (Optional)

```bash
# Trivy (scans Docker images)
trivy image legal-research-mcp:latest

# Snyk (commercial, free for open source)
snyk test

# Licenses (check license compatibility)
pip-licenses --format=csv --with-urls
```

---

## Troubleshooting

### Dependency Conflict

**Problem:** `error: Impossible to install: ...`

**Causes:**
- Package A requires X>=2.0
- Package B requires X<2.0
- Conflict = can't satisfy both

**Solution:**
```bash
# See what's conflicting
uv pip compile --verbose

# Option 1: Update both packages
uv add "package-a@latest" "package-b@latest"

# Option 2: Find middle ground
uv add "package-a>=2.1.0" "package-b>=1.9.0"

# Option 3: Remove one if not needed
uv remove package-b
```

### Build Fails After Update

**Problem:** `error: ModuleNotFoundError: No module named 'xxx'`

**Cause:** Changed API in updated dependency

**Solution:**
```bash
# 1. Find which package was updated
git diff uv.lock | grep "version"

# 2. Read changelog of that package
# Find breaking changes section

# 3. Update code to use new API
# Or pin to old version temporarily

# 4. Add regression test
# Ensure code works with updated package
```

### Docker Build Fails

**Problem:** `error: Could not find a version that satisfies the requirement`

**Cause:** Platform mismatch (e.g., Linux vs Mac wheels)

**Solution:**
```bash
# Regenerate lock file for target platform
uv pip compile --python-platform linux --python-version 3.12 pyproject.toml

# Or use multi-stage Docker build
# See Dockerfile for example
```

---

## Best Practices

### Version Constraints

✅ **Good:**
```toml
"fastapi>=0.109.0,<0.120"    # Allow minor updates, block majors
"pydantic>=2.0.0"            # Accept any 2.x (breaking on 3.x)
"pytest>=8.0.0"              # Accept any 8.x+ (dev dependency)
```

❌ **Bad:**
```toml
"fastapi==0.109.0"           # Too rigid, misses bug fixes
"fastapi>=0.100.0"           # Too loose, allows breaking changes
"fastapi"                    # No version constraint
```

### Production vs Development

✅ **Good split:**
```toml
[project]
dependencies = [
    "fastapi",
    "httpx",
    "pydantic",  # Keep small for production
]

[project.optional-dependencies]
dev = [
    "pytest",
    "ruff",
    "mypy",  # Heavier tools only in dev
]
```

❌ **Bad:**
```toml
[project]
dependencies = [
    "fastapi",
    "pytest",     # Testing tool in production!
    "jupyter",    # Analysis tool in production!
]
```

### Keeping Dependencies Minimal

**Review regularly:**
```bash
# Which packages are installed?
pip list

# Which are actually used?
grep -r "^import\|^from" app/ | grep -oE "[a-z_]+" | sort -u

# Anything unused?
# If yes, remove it!
```

**Strategy:**
- Start minimal
- Add only when necessary
- Remove when no longer needed
- Prefer built-ins when available

### Monitoring for Vulnerabilities

**Weekly:**
- Check Dependabot PRs
- Review security updates
- Run `safety check` locally

**Monthly:**
- Check major releases
- Update changelog
- Test with latest versions

**Quarterly:**
- Deep dependency audit
- Evaluate alternative packages
- Optimize for performance/security

---

## Dependency Checklist

Before committing dependency changes:

- [ ] Run `uv sync --dev`
- [ ] Run `uv run pytest`
- [ ] Run `uv run ruff check .`
- [ ] Run `uv run mypy app/`
- [ ] Run `uv run safety check`
- [ ] Check `uv.lock` for new transitive deps
- [ ] Verify no duplicate packages
- [ ] Ensure all deps are used (grep import statements)
- [ ] Document why new dependency is needed
- [ ] Update this guide if needed

---

## CI/CD Integration

### What Runs in CI

```yaml
# .github/workflows/ci.yml includes:
- ruff format --check .   # Code formatting
- ruff check .            # Code quality
- mypy --strict app/      # Type checking
- safety check            # Security scan (fails on vulns)
- pytest                  # Unit tests
```

### What Runs in Security CI

```yaml
# .github/workflows/integration-tests.yml:
- pytest -m integration   # Integration tests (requires API key)
```

### Branch Protection

Pull requests must pass all checks before merging:
- Lint ✅
- Type check ✅
- Unit tests ✅ (80% coverage)
- Security scan ✅

---

## Common Questions

### Q: Should I upgrade immediately when a new version is released?

A: Not necessarily. Wait for Dependabot to submit the PR, then review:
- Does it break our code?
- Does it fix important bugs or security issues?
- Can we test it?

### Q: What if a dependency has a security vulnerability?

A:
1. Dependabot should create a PR automatically
2. If it doesn't, run `safety check` to verify
3. Update to patched version
4. If no patch available, consider alternatives or workarounds

### Q: Can I use development dependencies in production?

A: No. They'll bloat the container and create vulnerabilities. Keep them dev-only.

### Q: How do I check if a package is maintained?

A: Check:
- GitHub repo: Recent commits? Active issues?
- PyPI: Last release date (should be < 1 year)
- Downloads: Popular = more eyes on security
- Community: Active discussions on GitHub?

### Q: What if updating a dependency breaks our code?

A:
1. Run local tests: `uv run pytest`
2. Find what changed: Read changelog
3. Update code to use new API
4. Or pin to previous working version temporarily

---

## Related Documentation

- [pyproject.toml](./pyproject.toml) - Dependency specification
- [.github/dependabot.yml](./.github/dependabot.yml) - Auto-update configuration
- [.github/workflows/ci.yml](./.github/workflows/ci.yml) - CI security scan
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Deployment with dependencies

---

**For security incident response, see [OPERATIONS.md](./OPERATIONS.md). For detailed deployment, see [DEPLOYMENT.md](./DEPLOYMENT.md).**
