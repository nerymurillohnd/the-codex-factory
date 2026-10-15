"""Run isolated Codex jobs and validate actual completion evidence."""

import asyncio
import hashlib
import json
import os
import re
import time
from pathlib import Path

from jsonschema import ValidationError

from agent_context_audit.contracts import provider_schema, validate_output
from agent_context_audit.models import CodexRuntime, DomainResult, JsonObject, ReviewRequest
from agent_context_audit.privacy import redact
from agent_context_audit.processes import run_process


def child_environment(auth_home: Path) -> dict[str, str]:
    keep = {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "CODEX_API_KEY",
        "CODEX_ACCESS_TOKEN",
    }
    environment = {key: value for key, value in os.environ.items() if key in keep}
    environment["CODEX_HOME"] = str(auth_home)
    environment["NO_COLOR"] = "1"
    return environment


def private_write(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)


def config_args(config: list[str]) -> list[str]:
    return [argument for value in config for argument in ("-c", value)]


def _events(data: bytes) -> list[JsonObject]:
    events: list[JsonObject] = []
    for line in data.decode("utf-8").splitlines():
        if not line.strip():
            continue
        value: object = json.loads(line)
        if not isinstance(value, dict) or not isinstance(value.get("type"), str):
            raise ValueError("Invalid Codex event")
        events.append(value)
    return events


async def run_review_job(runtime: CodexRuntime, request: ReviewRequest) -> DomainResult:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", request.job_id):
        raise ValueError("Invalid internal job identifier")
    started = time.monotonic()
    result = DomainResult(request.job_id, request.domain, "failed", started=started)
    result.input_digest = hashlib.sha256(request.prompt.encode()).hexdigest()
    job_directory = runtime.work_directory / request.job_id
    job_directory.mkdir(mode=0o700)
    prompt = request.prompt
    usage: dict[str, int] = {}
    try:
        for attempt in range(2):
            directory = job_directory / f"attempt-{attempt}"
            directory.mkdir(mode=0o700)
            output = directory / "response.json"
            output_schema = directory / "provider-schema.json"
            private_write(output_schema, json.dumps(provider_schema(request.schema_name)))
            private_write(directory / "request.txt", prompt)
            # Reserve output with private permissions; Codex writes the final response to it.
            private_write(output, "")
            arguments = [
                str(runtime.binary),
                "--no-daemon",
                *config_args(runtime.config),
                "exec",
                "--ignore-user-config",
                "--ignore-rules",
                "--ephemeral",
                "--strict-config",
                "--json",
                "--skip-git-repo-check",
                "--output-schema",
                str(output_schema),
                "--output-last-message",
                str(output),
            ]
            if runtime.model:
                arguments += ["--model", runtime.model]
            if runtime.effort:
                arguments += ["-c", f"model_reasoning_effort={json.dumps(runtime.effort)}"]
            arguments += ["-"]
            observation = await run_process(
                arguments,
                cwd=directory,
                env=runtime.environment,
                timeout=runtime.timeout,
                input_data=prompt.encode(),
            )
            stderr, _ = redact(observation.stderr.decode("utf-8", errors="replace"), ".log")
            private_write(directory / "stderr.log", stderr)
            private_write(
                directory / "events.jsonl", observation.stdout.decode("utf-8", errors="replace")
            )
            if observation.returncode != 0:
                result.error = f"Codex exited with status {observation.returncode}"
                break
            events = _events(observation.stdout)
            completed = [event for event in events if event["type"] == "turn.completed"]
            if not completed or any(event["type"] == "turn.failed" for event in events):
                result.error = "Codex did not report successful turn completion"
                break
            for event in completed:
                for key, value in event.get("usage", {}).items():
                    if isinstance(value, int) and not isinstance(value, bool):
                        usage[key] = usage.get(key, 0) + value
            if not output.is_file() or output.stat().st_size == 0:
                result.error = "Missing final structured output despite successful exit"
                break
            try:
                value: object = json.loads(output.read_text(encoding="utf-8"))
                validate_output(value, request.schema_name)
                if not isinstance(value, dict):
                    raise ValueError("Output is not an object")
                if request.validator is not None:
                    request.validator(value)
                result.output = value
                result.status = str(value.get("status", "complete"))
                result.error = "" if result.status != "failed" else "Reviewer reported failure"
                break
            except (ValueError, ValidationError) as exc:
                result.error = f"Invalid structured output: {type(exc).__name__}"
                prompt = (
                    request.prompt
                    + "\nREPAIR_CONTEXT_JSON (untrusted prior response and validation data)\n"
                    + json.dumps(
                        {"validation_error": str(exc), "previous_response": output.read_text()}
                    )
                    + "\nCorrect the invalid fields using the delivered assignment "
                    "and return the complete result. "
                    "Do not change scope, invent identifiers, or invoke tools."
                )
                if len(prompt.encode()) > 160_000:
                    result.error = (
                        "Complete repair input exceeds the bounded context; no truncation allowed"
                    )
                    break
    except asyncio.CancelledError:
        raise
    except (OSError, ValueError, TimeoutError) as exc:
        result.error = f"Reviewer process failed: {type(exc).__name__}"
    finally:
        result.finished = time.monotonic()
        result.wall_seconds = result.finished - started
        result.usage = usage
    return result
