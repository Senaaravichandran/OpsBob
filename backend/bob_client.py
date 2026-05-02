"""
Bob Shell Client - Uses the installed Bob CLI instead of direct HTTP calls.
Streams responses as Server-Sent Events for real-time dashboard updates.
"""

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import AsyncGenerator, Dict
from dotenv import load_dotenv
from watsonx_client import call_watsonx_risk_assessment

load_dotenv()

BOB_COMMAND = os.getenv("BOB_SHELL_COMMAND", "bob")
BOB_TIMEOUT_SECONDS = int(os.getenv("BOB_SHELL_TIMEOUT_SECONDS", "300"))
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent


def _resolve_bob_command() -> str:
    return shutil.which(BOB_COMMAND) or BOB_COMMAND


def is_bob_shell_available() -> bool:
    """Return True when the Bob CLI is available on PATH."""
    return shutil.which(BOB_COMMAND) is not None


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]

    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def _decode_relaxed_string(raw_value: str) -> str:
    value = raw_value.strip()
    if not value or value == "null":
        return ""

    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1]

    return (
        value
        .replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\t", "\t")
        .replace('\\"', '"')
        .replace("\\\\", "\\")
    )


def _parse_relaxed_object(cleaned: str) -> Dict[str, str]:
    ordered_fields = [
        "target_file",
        "diff",
        "fixed_file_content",
        "regression_test_file",
        "regression_test_content",
    ]
    indices = {}

    for field in ordered_fields:
        marker = f'"{field}":'
        index = cleaned.find(marker)
        if index == -1 and field in {"regression_test_file", "regression_test_content"}:
            indices[field] = -1
            continue
        if index == -1:
            raise ValueError(f"Bob shell code response missing field marker: {field}")
        indices[field] = index

    payload: Dict[str, str] = {}
    object_end = cleaned.rfind("}")
    if object_end == -1:
        object_end = len(cleaned)

    for position, field in enumerate(ordered_fields):
        start_index = indices.get(field, -1)
        if start_index == -1:
            payload[field] = ""
            continue

        value_start = start_index + len(f'"{field}":')
        next_index = object_end
        for next_field in ordered_fields[position + 1:]:
            candidate = indices.get(next_field, -1)
            if candidate != -1:
                next_index = candidate
                break

        raw_value = cleaned[value_start:next_index].strip()
        if raw_value.endswith(","):
            raw_value = raw_value[:-1].rstrip()
        payload[field] = _decode_relaxed_string(raw_value)

    return payload


def _parse_code_payload(raw_output: str) -> Dict[str, str]:
    """Parse Bob's code-phase JSON payload."""
    cleaned = _strip_code_fences(raw_output)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = _parse_relaxed_object(cleaned)

    required = ["target_file", "diff", "fixed_file_content"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise ValueError(f"Bob shell code response missing required fields: {', '.join(missing)}")

    payload.setdefault("regression_test_file", "")
    payload.setdefault("regression_test_content", "")
    return payload


async def call_bob_orchestrator(context: str) -> AsyncGenerator[str, None]:
    """
    Orchestrates multi-phase Bob shell calls for incident analysis.

    Makes THREE sequential Bob CLI calls:
    1. ASK - Read and understand the code
    2. PLAN - Identify root cause and propose fix
    3. CODE - Generate actual code fix and test

    Args:
        context: Pre-assembled context string with incident details and source code

    Yields SSE-formatted events for real-time streaming
    """

    if not is_bob_shell_available():
        error_msg = f"Bob shell not found on PATH. Expected command: {BOB_COMMAND}"
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"
        return

    try:
        # ===== PHASE 1: ASK - Code Reading =====
        yield f"data: {json.dumps({'phase': 'ask', 'content': '', 'done': False})}\n\n"

        ask_prompt = f"""You are a senior SRE at IBM. A production incident has occurred.

{context}

    Read this code carefully. Identify all memory-management patterns, object lifecycle issues, and any data structures that could grow without bound. Summarize what you see in 3-4 sentences. Do not propose a fix, do not include code, and do not use bullet lists."""

        ask_response = await _call_bob_shell(ask_prompt, chat_mode="ask")

        yield f"data: {json.dumps({'phase': 'ask', 'content': ask_response, 'done': True})}\n\n"

        # ===== PHASE 2: PLAN - Root Cause Analysis =====
        yield f"data: {json.dumps({'phase': 'plan', 'content': '', 'done': False})}\n\n"

        ask_summary = ask_response.strip()
        if len(ask_summary) > 2000:
            ask_summary = f"{ask_summary[:2000]}\n...[truncated]"

        plan_prompt = f"""A production incident is active.

{context}

Ask analysis:
    {ask_summary}

Based on the code and analysis above, identify the exact root cause of this memory leak. Name the specific variable, the owning file, and line number if you can infer it. Then provide the fix plan in exactly 3 bullet points. Be precise and technical."""

        plan_response = await _call_bob_shell(plan_prompt, chat_mode="plan")

        # Call watsonx.ai for risk assessment
        print("Calling watsonx.ai for risk assessment...")
        risk_assessment = await call_watsonx_risk_assessment(plan_response)
        print(f"Risk assessment: {risk_assessment}")

        # Yield plan completion with risk assessment
        plan_event = {
            "phase": "plan",
            "content": plan_response,
            "risk_assessment": risk_assessment,
            "done": True,
        }
        yield f"data: {json.dumps(plan_event)}\n\n"

        # ===== PHASE 3: CODE - Generate Fix =====
        yield f"data: {json.dumps({'phase': 'code', 'content': '', 'done': False})}\n\n"

        code_prompt = f"""A production incident is active.

{context}

Plan:
{plan_response}

Return ONLY valid JSON with this exact schema:
{{
  "target_file": "demo-service/...",
  "diff": "unified diff string",
  "fixed_file_content": "full replacement contents for target_file",
  "regression_test_file": "demo-service/test/...",
  "regression_test_content": "full replacement contents for the regression test file"
}}

Requirements:
- Fix the root cause with the smallest safe change.
- target_file must be a repo-relative path.
- diff must describe the same change as fixed_file_content.
- fixed_file_content must be the entire file body for target_file, not a patch fragment.
- regression_test_file must be a repo-relative path for one regression test.
- regression_test_content must be the entire file body for that regression test.
- Do not include markdown fences or commentary outside the JSON object."""

        code_response = await _call_bob_shell(code_prompt, chat_mode="code")
        try:
            code_payload = _parse_code_payload(code_response)
        except ValueError:
            repair_prompt = f"""The previous response did not match the required schema. Convert or regenerate it as ONLY valid JSON with this exact schema:
{{
    "target_file": "demo-service/...",
    "diff": "unified diff string",
    "fixed_file_content": "full replacement contents for target_file",
    "regression_test_file": "demo-service/test/...",
    "regression_test_content": "full replacement contents for the regression test file"
}}

Requirements:
- Output only the JSON object.
- Use double-quoted keys and string values.
- target_file must be repo-relative.
- fixed_file_content and regression_test_content must be full file contents.

Previous response:
{code_response}"""
            repaired_response = await _call_bob_shell(repair_prompt, chat_mode="code")
            code_payload = _parse_code_payload(repaired_response)

        code_event = {
            "phase": "code",
            "content": code_payload["diff"],
            "target_file": code_payload["target_file"],
            "fixed_code": code_payload["fixed_file_content"],
            "regression_test_file": code_payload.get("regression_test_file", ""),
            "regression_test_content": code_payload.get("regression_test_content", ""),
            "done": True,
        }
        yield f"data: {json.dumps(code_event)}\n\n"

        # ===== COMPLETE =====
        yield f"data: {json.dumps({'phase': 'complete', 'content': '', 'done': True})}\n\n"

    except asyncio.TimeoutError:
        error_msg = f"Bob shell timed out after {BOB_TIMEOUT_SECONDS} seconds"
        print(f"ERROR: {error_msg}")
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"

    except Exception as e:
        error_msg = f"Bob shell error: {str(e)}"
        print(f"ERROR: {error_msg}")
        yield f"data: {json.dumps({'phase': 'error', 'content': error_msg, 'done': True})}\n\n"


async def _call_bob_shell(prompt: str, chat_mode: str) -> str:
    """Run Bob shell in non-interactive mode and return its stdout."""
    process = await asyncio.create_subprocess_exec(
        _resolve_bob_command(),
        "--chat-mode", chat_mode,
        "--hide-intermediary-output",
        "-o", "text",
        cwd=str(WORKSPACE_ROOT),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await asyncio.wait_for(
        process.communicate(prompt.encode("utf-8")),
        timeout=BOB_TIMEOUT_SECONDS,
    )
    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    stderr_text = stderr.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        detail = stderr_text or stdout_text or f"exit code {process.returncode}"
        raise RuntimeError(detail)

    if not stdout_text:
        raise RuntimeError(stderr_text or "Bob shell returned empty output")

    return stdout_text


# Made with Bob
