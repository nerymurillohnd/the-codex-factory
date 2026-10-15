"""Actual Codex binary checks; a local synthetic provider is not semantic model evidence."""

import asyncio
import json
import shutil

import pytest
from agent_context_audit.isolation import inspect_claude_version, prepare_runtime, probe_isolation
from agent_context_audit.models import ReviewRequest, RunOptions
from agent_context_audit.report import create_run
from agent_context_audit.runtime import run_review_job

from tests.test_contracts import empty_result


def test_native_sandbox_and_exact_worker_transport(context_tree, tmp_path, native_codex):
    target, roots = context_tree
    options = RunOptions(
        target, roots, tmp_path / "runs", tmp_path / "auth", native_codex, job_timeout=30
    )
    run = create_run(target, options.output_dir)
    requests = []

    async def handler(reader, writer):
        try:
            header = await reader.readuntil(b"\r\n\r\n")
            size = next(
                (
                    int(line.split(b":", 1)[1])
                    for line in header.split(b"\r\n")
                    if line.lower().startswith(b"content-length:")
                ),
                0,
            )
            payload = json.loads(await reader.readexactly(size))
            requests.append(payload)
            message = {
                "id": "msg_fixture",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {"type": "output_text", "text": json.dumps(empty_result()), "annotations": []}
                ],
            }
            response = {
                "id": "resp_fixture",
                "object": "response",
                "status": "completed",
                "output": [message],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            }
            events = [
                {
                    "type": "response.created",
                    "response": dict(response, status="in_progress", output=[]),
                },
                {
                    "type": "response.output_item.added",
                    "output_index": 0,
                    "item": dict(message, status="in_progress", content=[]),
                },
                {
                    "type": "response.output_text.delta",
                    "item_id": "msg_fixture",
                    "output_index": 0,
                    "content_index": 0,
                    "delta": json.dumps(empty_result()),
                },
                {"type": "response.output_item.done", "output_index": 0, "item": message},
                {"type": "response.completed", "response": response},
            ]
            wire = "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: "
                + str(len(wire)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + wire
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def exercise():
        runtime = await prepare_runtime(options, run)
        capability = await probe_isolation(runtime)
        assert capability.verified, capability.limitations
        server = await asyncio.start_server(handler, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            runtime.config += [
                'model_provider="audit_transport_fixture"',
                'model="fixture-model"',
                'model_providers.audit_transport_fixture.name="Local transport fixture"',
                f'model_providers.audit_transport_fixture.base_url="http://127.0.0.1:{port}/v1"',
                'model_providers.audit_transport_fixture.wire_api="responses"',
                "model_providers.audit_transport_fixture.requires_openai_auth=false",
            ]
            runtime.environment.pop("CODEX_API_KEY", None)
            runtime.environment.pop("CODEX_ACCESS_TOKEN", None)
            observed = await run_review_job(
                runtime,
                ReviewRequest("native-transport", "D1", "Return an empty structured audit result."),
            )
            assert observed.status == "complete", observed.error
            assert observed.usage["input_tokens"] == 10
            assert len(requests) == 1
            names = {tool.get("name", tool.get("type")) for tool in requests[0].get("tools", [])}
            assert names <= {"request_user_input"}, names
            assert requests[0].get("text", {}).get("format", {}).get("type") == "json_schema"
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())


def test_native_optional_claude_version_runs_in_isolated_home(context_tree, tmp_path, native_codex):
    if not shutil.which("claude"):
        pytest.skip("Optional native Claude CLI is not installed; file-only mode remains supported")
    target, roots = context_tree
    options = RunOptions(target, roots, tmp_path / "runs", tmp_path / "auth", native_codex)

    async def exercise():
        run = create_run(target, options.output_dir)
        runtime = await prepare_runtime(options, run)
        result = await inspect_claude_version(runtime, target.root)
        assert result["verified"], result
        assert result["version"]
        assert list((run.work_directory / "claude-version-home").iterdir()) == []

    asyncio.run(exercise())
