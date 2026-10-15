# Security and privacy

Do not open public issues containing credentials, authentication stores, real .env files or private audit reports. Prefer a minimal synthetic reproduction. Until a private reporting channel is published, contact the repository owner without including sensitive payloads and agree on a suitable private channel first.

Audit sources and model outputs are untrusted. Source declarations never authorize execution or wider filesystem/network access. The plugin must fail visibly when isolation, provenance, redaction or output integrity cannot be established. Do not bypass a managed restriction or weaken a quality gate to make a run pass.

Reports include proposed edits and selected sanitized excerpts. Keep the private run directory private. The model provider receives sanitized context as part of native Codex execution; filesystem isolation is not a promise about provider retention or host-wide telemetry.
