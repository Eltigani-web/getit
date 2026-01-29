# Production Readiness Scorecard

**Project:** getit - Universal file hosting downloader with CLI+TUI
**Assessment Date:** January 2026
**Overall Readiness Score:** 4/10
**Status:** ⚠️ **Requires Significant Hardening**

---

## Executive Summary

GetIt is a feature-rich file downloader supporting multiple hosting services (GoFile, PixelDrain, MediaFire, 1Fichier, Mega.nz) with both CLI and TUI interfaces. While functional for personal use, the codebase requires substantial improvements before being production-ready for long-lived container deployments or enterprise environments.

**Key Gaps:**
- Networking lacks proxy/TLS configuration, uneven backoff across providers
- Security weaknesses: plaintext credentials, permissive file permissions, no encryption at rest
- Packaging incomplete: broken Homebrew formula, missing Docker image, no changelog
- Observability minimal: no structured logging, no healthchecks

**Critical Path:** Networking hardening → Security hardening → Packaging automation → Observability → Tests/coverage

---

## Scorecard by Category

| Category | Score | Status | Priority | Wave |
|----------|-------|--------|----------|------|
| **Networking** | 5/10 | ⚠️ Partial | High | 2-3 |
| **Security** | 3/10 | 🚨 Critical | Critical | 4 |
| **Packaging** | 2/10 | 🚨 Critical | High | 5-6 |
| **Observability** | 2/10 | 🚨 Critical | High | 1-7 |
| **Testing** | 4/10 | ⚠️ Partial | Medium | 7 |

---

## Detailed Risk Register

### 1. Networking (Score: 5/10)

#### Current State
- ✅ Global rate limiter implemented (AsyncLimiter, 10 rps default)
- ✅ Retry logic with exponential backoff for 429 responses
- ✅ Timeout configuration available (30s connect, 300s read)
- ✅ HTTP Range resume support in downloader

#### Risks

| Risk | Severity | Impact | Owner |
|------|----------|--------|-------|
| **R1.1: No proxy support** | High | Cannot route through corporate proxies, violates enterprise requirements | Networking |
| **R1.2: TLS CA configuration not exposed** | High | Cannot use custom CA bundles in regulated environments | Networking |
| **R1.3: Timeout not wired from settings** | Medium | Default timeouts may not suit all network conditions | Networking |
| **R1.4: Uneven backoff across extractors** | Medium | Inconsistent retry behavior, may trigger provider rate limits | Networking |
| **R1.5: No per-provider rate limit configuration** | Medium | Cannot fine-tune per-host limits (e.g., Mega is more restrictive) | Networking |
| **R1.6: No user-agent versioning** | Low | Harder to debug issues, may be blocked by providers | Networking |

#### Mitigations

| Risk | Mitigation | Priority | Effort |
|------|------------|----------|--------|
| R1.1 | Expose `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` env vars via `trust_env=True` | High | Low |
| R1.2 | Add `SSL_CERT_FILE` and custom CA bundle support in HTTP client | High | Low |
| R1.3 | Wire `Settings.timeout` to `HTTPClient` initialization | Medium | Low |
| R1.4 | Standardize backoff: exp+jitter capped at 30-60s across all extractors | High | Medium |
| R1.5 | Add per-provider rate limit overrides in config | Medium | Medium |
| R1.6 | Add versioned User-Agent header from `__version__` | Low | Trivial |

---

### 2. Security (Score: 3/10)

#### Current State
- ✅ Mega.nz AES-CTR decryption implemented
- ✅ Password handling for protected files
- ⚠️  File permissions: 644 for downloads (world-readable)
- ⚠️  Database: No WAL, no PRAGMAs, no schema versioning

#### Risks

| Risk | Severity | Impact | Owner |
|------|----------|--------|-------|
| **R2.1: Plaintext credentials in config** | Critical | Passwords/tokens stored in plain JSON, readable by any user | Security |
| **R2.2: Permissive file permissions** | High | Downloads (644) and config (default) readable by all users | Security |
| **R2.3: No encryption at rest** | High | History database stores URLs, filenames in plain text | Security |
| **R2.4: SQLite without WAL/PRAGMAs** | Medium | Corruption risk in concurrent scenarios, no busy_timeout | Security |
| **R2.5: Secrets in logs** | High | Environment variables may leak into error logs | Security |
| **R2.6: No input validation on URLs** | Medium | Potential for SSRF or injection attacks | Security |
| **R2.7: No schema versioning** | Low | Migration issues on database changes | Security |

#### Mitigations

| Risk | Mitigation | Priority | Effort |
|------|------------|----------|--------|
| R2.1 | Redact secrets in logs, add optional encryption hook for config.json | Critical | Medium |
| R2.2 | Set 600 permissions for config/history, 640 for downloads (optional) | High | Low |
| R2.3 | Add opt-in encryption for SQLite database (documented approach) | High | High |
| R2.4 | Enable WAL, set busy_timeout=30s, add PRAGMA synchronous=NORMAL | Medium | Low |
| R2.5 | Add secret redaction middleware in logging layer | High | Low |
| R2.6 | Add URL validation whitelist/sanitization | Medium | Low |
| R2.7 | Add schema_version table and migration hooks | Low | Low |

---

### 3. Packaging (Score: 2/10)

#### Current State
- ✅ PyPI package exists (`getit-cli`)
- ✅ Basic pyproject.toml configuration
- ✅ Homebrew tap exists (`ahmedeltigani/getit`)
- ⚠️  Version duplicated across files
- ⚠️  No changelog
- ❌ No Docker image
- ❌ Homebrew formula has issues (placeholders, license mismatch)

#### Risks

| Risk | Severity | Impact | Owner |
|------|----------|--------|-------|
| **R3.1: Version duplication** | Medium | Risk of version drift between pyproject.toml, __init__.py, formula | Packaging |
| **R3.2: No changelog** | Medium | Users cannot track changes, releases lack context | Packaging |
| **R3.3: Homebrew formula broken** | High | License mismatch (GPLv3 vs MIT), placeholders not filled | Packaging |
| **R3.4: No Docker image** | High | Cannot deploy as container, blocks long-lived worker mode | Packaging |
| **R3.5: No automated release process** | Medium | Manual release process prone to errors | Packaging |
| **R3.6: MANIFEST.in missing** | Low | May exclude essential files from PyPI package | Packaging |

#### Mitigations

| Risk | Mitigation | Priority | Effort |
|------|------------|----------|--------|
| R3.1 | Single source of truth: version from git tags, update all from one place | High | Medium |
| R3.2 | Create CHANGELOG.md, auto-update with release notes | Medium | Low |
| R3.3 | Fix Homebrew formula: correct license to GPLv3, fill url/sha placeholders | High | Low |
| R3.4 | Create Dockerfile (debian-slim, non-root, healthcheck, worker entrypoint) | High | Medium |
| R3.5 | Document release automation steps for PyPI, Homebrew, Docker Hub | Medium | Medium |
| R3.6 | Add MANIFEST.in if needed, verify package contents | Low | Trivial |

---

### 4. Observability (Score: 2/10)

#### Current State
- ❌ No structured logging
- ❌ No request/download correlation IDs
- ❌ No healthcheck endpoint
- ❌ No graceful shutdown signals
- ✅ Basic print statements in TUI

#### Risks

| Risk | Severity | Impact | Owner |
|------|----------|--------|-------|
| **R4.1: No structured logging** | High | Cannot debug production issues, no log aggregation support | Observability |
| **R4.2: No correlation IDs** | High | Cannot trace requests across downloads | Observability |
| **R4.3: No healthcheck** | High | Container orchestrators cannot detect worker health | Observability |
| **R4.4: No graceful shutdown** | High | Data corruption risk on SIGTERM/KILL | Observability |
| **R4.5: ANSI codes in non-TTY logs** | Medium | Breaks log parsing in CI/containers | Observability |
| **R4.6: No metrics (by design)** | Low | Acceptable for this phase, but limits operational insight | Observability |

#### Mitigations

| Risk | Mitigation | Priority | Effort |
|------|------------|----------|--------|
| R4.1 | Add structured logging: JSON for non-TTY, plain for TTY, run_id + download_id | High | Medium |
| R4.2 | Generate unique run_id per session, download_id per file | High | Low |
| R4.3 | Implement healthcheck command for Docker (check worker status) | High | Low |
| R4.4 | Add SIGTERM handler with graceful shutdown (complete current chunks) | High | Medium |
| R4.5 | Detect TTY, disable ANSI when `NO_COLOR=1` or stdout not TTY | Medium | Low |
| R4.6 | Document metrics as future work (out of scope for this phase) | Low | N/A |

---

### 5. Testing (Score: 4/10)

#### Current State
- ✅ pytest framework configured
- ✅ ruff and mypy for linting/type-checking
- ✅ CI budget constraints defined (5m lint, 10m tests)
- ⚠️  No coverage gate
- ⚠️  Provider tests not marked as slow
- ⚠️  May exceed CI budgets with current test load

#### Risks

| Risk | Severity | Impact | Owner |
|------|----------|--------|-------|
| **R5.1: No coverage gate** | Medium | Regressions undetected, code quality drift | Testing |
| **R5.2: CI timeouts likely** | Medium | Long tests break CI automation | Testing |
| **R5.3: No slow test markers** | Medium | Cannot run fast-only suites in PRs | Testing |
| **R5.4: Limited provider test coverage** | Low | Extractor bugs may reach production | Testing |

#### Mitigations

| Risk | Mitigation | Priority | Effort |
|------|------------|----------|--------|
| R5.1 | Add coverage reporting with 75% target (optional gate) | Medium | Low |
| R5.2 | Mark slow/provider tests, gate with `SLOW_PROVIDER_TESTS=1` | Medium | Low |
| R5.3 | Add pytest markers (`@pytest.mark.slow`, `@pytest.mark.provider`) | Medium | Low |
| R5.4 | Add stubbed unit tests for all extractors (fast) | Low | Medium |

---

## Mitigation Owners & Tracking

| Wave | Task | Owner(s) | Estimated Effort | Dependencies |
|------|------|----------|-----------------|--------------|
| 0 | Scorecard & baseline docs | Orchestrator | Done | - |
| 1 | Structured logging + config wiring | Quick/Unspecified | Small/Medium | 0 |
| 2 | Global HTTP client hardening | Quick | Medium | 1 |
| 3a | GoFile, PixelDrain hardening | Quick | Medium | 2 |
| 3b | 1Fichier, MediaFire, Mega hardening | Quick | Medium | 2 |
| 4 | Storage/config security | Unspecified | Small/Medium | 3a/3b |
| 5 | Packaging/versioning/changelog/Homebrew | Unspecified | Small/Medium | 4 |
| 6 | Docker long-lived worker | Unspecified | Medium | 5 |
| 7 | Tests & coverage within CI budgets | Quick | Small/Medium | 5/6 |

---

## Definition of Done

The project will be considered production-ready when:

- [ ] **Networking**: All proxy/TLS configs exposed, per-provider rate limits standardized, backoff consistent
- [ ] **Security**: Config/history permissions tightened (600), WAL enabled, secrets redacted from logs
- [ ] **Packaging**: Docker image builds, Homebrew formula fixed, changelog maintained, version automation in place
- [ ] **Observability**: Structured logging with run_id/download_id, healthcheck available, graceful shutdown works
- [ ] **Testing**: Coverage >=75%, CI passes within budgets (5m lint, 10m tests), slow tests gated
- [ ] **CI/CD**: All checks green on Python 3.11-3.13 matrix

---

## Next Steps

1. **Immediate (Wave 0):** This scorecard accepted and linked from README
2. **Short-term (Waves 1-3):** Networking hardening + structured logging
3. **Medium-term (Waves 4-6):** Security hardening + packaging automation
4. **Long-term (Wave 7):** Test coverage + CI optimization

---

**Document Version:** 1.0
**Last Updated:** 2026-01-29
**Review Cycle:** Update monthly or after each production release
