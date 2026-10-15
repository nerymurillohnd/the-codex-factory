"""Bounded subprocess capture and cancellation for owned local children."""

import asyncio
import os
import signal
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes


async def run_process(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: float,
    input_data: bytes | None = None,
    max_output: int = 8 * 1024 * 1024,
) -> ProcessResult:
    process = await asyncio.create_subprocess_exec(
        *args,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )

    async def collect(stream: asyncio.StreamReader | None) -> bytes:
        if stream is None:
            raise RuntimeError("Process pipe unavailable")
        chunks: list[bytes] = []
        size = 0
        while data := await stream.read(65536):
            size += len(data)
            if size > max_output:
                raise ValueError("Process exceeded output limit")
            chunks.append(data)
        return b"".join(chunks)

    async def send() -> None:
        if process.stdin is not None:
            try:
                if input_data:
                    process.stdin.write(input_data)
                    await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()

    readers = [
        asyncio.create_task(collect(process.stdout)),
        asyncio.create_task(collect(process.stderr)),
    ]
    writer = asyncio.create_task(send())
    completed = False
    try:
        await asyncio.wait_for(
            asyncio.gather(readers[0], readers[1], writer, process.wait()), timeout
        )
        completed = True
        return ProcessResult(
            process.returncode if process.returncode is not None else -1,
            readers[0].result(),
            readers[1].result(),
        )
    finally:
        if not completed or process.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            if not completed:
                await asyncio.sleep(0.2)
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                await process.wait()
        for task in [*readers, writer]:
            if not task.done():
                task.cancel()
        await asyncio.gather(readers[0], readers[1], writer, return_exceptions=True)
