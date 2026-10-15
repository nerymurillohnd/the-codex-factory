"""Typed boundaries shared by discovery, review, and reporting."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class Target:
    root: Path
    cwd: Path


@dataclass(frozen=True)
class SourceRoots:
    codex: Path
    claude: Path
    user_home: Path
    additional: tuple[Path, ...] = ()
    claude_state: Path | None = None


@dataclass
class Reference:
    target: str
    line: int
    kind: str
    state: str
    resolved: str | None = None


@dataclass
class SourceRecord:
    source_id: str
    path: Path
    canonical_path: Path
    scope: str
    domain: str
    hosts: list[str]
    load_mode: str = "always"
    provenance: str = "user-owned"
    sha256: str = ""
    line_count: int = 0
    byte_count: int = 0
    status: str = "pending"
    reason: str = ""
    references: list[Reference] = field(default_factory=list)
    redacted_lines: list[int] = field(default_factory=list)
    contexts: list[str] = field(default_factory=list)


@dataclass
class Inventory:
    target: Target
    roots: SourceRoots
    sources: list[SourceRecord] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    exclusions: list[JsonObject] = field(default_factory=list)
    repository_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    source_id: str
    line_start: int
    line_end: int
    byte_start: int
    byte_end: int
    text: str
    payload_sha256: str


@dataclass(frozen=True)
class Directive:
    directive_id: str
    source_id: str
    line_start: int
    line_end: int
    text: str
    chunk_id: str = ""


@dataclass(frozen=True)
class Observation:
    observation_id: str
    kind: str
    primary_source_id: str
    locations: list[JsonObject]
    evidence_refs: list[str]
    text: str


@dataclass
class ObservationDecision:
    observation_id: str
    outcome: str
    rationale: str
    evidence_refs: list[str]
    finding_indexes: list[int] = field(default_factory=list)
    finding_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReviewPackage:
    package_id: str
    source_id: str
    chunk_ids: list[str]
    directive_ids: list[str]
    observation_ids: list[str]
    context: list[JsonObject] = field(default_factory=list)


@dataclass
class AuditSnapshot:
    inventory: Inventory
    texts: dict[str, str]
    chunks: list[Chunk]
    directives: list[Directive]
    facts: list[JsonObject] = field(default_factory=list)
    initial_git: JsonObject = field(default_factory=dict)
    observations: list[Observation] = field(default_factory=list)


@dataclass
class KnowledgeBundle:
    data: JsonObject
    observations: list[JsonObject] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    documents: dict[str, str] = field(default_factory=dict)


@dataclass
class DomainResult:
    job_id: str
    domain: str
    status: str
    output: JsonObject = field(default_factory=dict)
    input_digest: str = ""
    error: str = ""
    usage: JsonObject = field(default_factory=dict)
    wall_seconds: float = 0
    started: float = 0
    finished: float = 0
    assigned_chunks: list[str] = field(default_factory=list)
    assigned_directives: list[str] = field(default_factory=list)
    assigned_observations: list[str] = field(default_factory=list)


DomainResults = list[DomainResult]


@dataclass
class ReconciledAudit:
    findings: list[JsonObject]
    dispositions: list[JsonObject]
    limitations: list[str] = field(default_factory=list)
    dissent: list[JsonObject] = field(default_factory=list)
    considered_job_ids: list[str] = field(default_factory=list)
    decisions: list[JsonObject] = field(default_factory=list)
    jobs: list[DomainResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    observation_decisions: list[JsonObject] = field(default_factory=list)
    assessments: list[JsonObject] = field(default_factory=list)
    adjudications: list[JsonObject] = field(default_factory=list)


@dataclass(frozen=True)
class SemanticAssessment:
    target_id: str
    target_digest: str
    verdict: str
    rationale: str
    evidence: list[JsonObject]
    counterevidence: list[JsonObject]


@dataclass
class VerificationResult:
    assessments: list[JsonObject] = field(default_factory=list)
    jobs: list[DomainResult] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


@dataclass
class RunOptions:
    target: Target
    roots: SourceRoots
    output_dir: Path
    auth_home: Path
    codex_bin: Path
    jobs: int = 4
    model: str | None = None
    effort: str | None = None
    challenge_rounds: int = 1
    job_timeout: int = 600
    timeout: int = 1800
    offline: bool = False
    allow_domains: tuple[str, ...] = ()
    baseline: Path | None = None
    entry_mode: str = "headless"
    allow_output_in_target: bool = False


@dataclass
class RunState:
    directory: Path
    work_directory: Path
    run_id: str
    repository_id: str
    created_at: str


@dataclass
class CodexRuntime:
    binary: Path
    auth_home: Path
    work_directory: Path
    config: list[str]
    environment: dict[str, str]
    version: str
    model: str | None = None
    effort: str | None = None
    timeout: int = 600


@dataclass
class ReviewRequest:
    job_id: str
    domain: str
    prompt: str
    schema_name: str = "domain"
    validator: Callable[[JsonObject], None] | None = field(default=None, repr=False)


@dataclass
class CapabilityReport:
    verified: bool
    checks: JsonObject
    limitations: list[str] = field(default_factory=list)


@dataclass
class CoverageResult:
    complete: bool
    errors: list[str]


@dataclass
class Baseline:
    findings: list[JsonObject]
    history: dict[str, str] = field(default_factory=dict)
    scope_fingerprint: str | None = None


@dataclass
class BaselineChanges:
    new: list[str] = field(default_factory=list)
    resolved: list[str] = field(default_factory=list)
    persisting: list[str] = field(default_factory=list)
    regressed: list[str] = field(default_factory=list)
    unassessed: list[str] = field(default_factory=list)


@dataclass
class RunOutcome:
    status: str
    exit_code: int
    report_path: Path | None
    result: JsonObject


@dataclass(frozen=True)
class RuntimePaths:
    codex: Path
    uv: Path
    plugin: Path


@dataclass(frozen=True)
class CalendarSpec:
    hour: int = 9
    minute: int = 0
    weekday: str | None = None
