import asyncio
import json
import os
import re
import uuid
from typing import Any

from opik import Opik
from opik.evaluation import evaluate
from opik.evaluation.metrics import (
    AgentToolCorrectnessJudge,
    AnswerRelevance,
    Usefulness,
    score_result,
)
from opik.evaluation.scorers import ScorerWrapperMetric

from app.core.config import settings
from app.services.agent_service import AgentService


DATASET_NAME = "leedhee-dataset"
EXPERIMENT_NAME = "leedhee-eval-v6"


def configure_opik() -> None:
    opik_settings = settings.OPIK
    if not opik_settings:
        return

    if opik_settings.URL_OVERRIDE:
        os.environ["OPIK_URL_OVERRIDE"] = opik_settings.URL_OVERRIDE
    if opik_settings.API_KEY:
        os.environ["OPIK_API_KEY"] = opik_settings.API_KEY
    if opik_settings.WORKSPACE:
        os.environ["OPIK_WORKSPACE"] = opik_settings.WORKSPACE


def build_tool_trace_payload(
    user_input: str,
    final_answer: str,
    tool_events: list[dict[str, Any]],
) -> str:
    trace_lines = [f"USER: {user_input}"]

    for event in tool_events:
        event_type = event.get("type")
        if event_type == "model":
            trace_lines.append(f"MODEL_TOOL_CALLS: {event.get('tool_calls', [])}")
            continue

        if event_type == "tool":
            trace_lines.append(
                f"TOOL {event.get('name')}: {event.get('content')}"
            )

    trace_lines.append(f"FINAL_ANSWER: {final_answer}")
    return "\n".join(trace_lines)


def parse_stream_chunk(chunk: str) -> dict[str, Any] | None:
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        # AgentService currently emits tool events with raw content that is not
        # valid JSON. Parse the stable prefix and preserve the tool payload as text.
        if '"step": "tools"' not in chunk:
            return None

        name_match = re.search(r'"name":\s*"([^"]+)"', chunk)
        content_marker = '"content":'
        content_index = chunk.find(content_marker)
        if content_index == -1:
            return None

        raw_content = chunk[content_index + len(content_marker) :].strip()
        if raw_content.endswith("}"):
            raw_content = raw_content[:-1].rstrip()

        return {
            "step": "tools",
            "name": name_match.group(1) if name_match else None,
            "content": raw_content,
        }


async def run_agent_query(
    agent_service: AgentService, user_input: str
) -> dict[str, str]:
    tool_events: list[dict[str, Any]] = []

    async for chunk in agent_service.process_query(
        user_input,
        uuid.uuid4(),
    ):
        payload = parse_stream_chunk(chunk)
        if payload is None:
            continue

        step = payload.get("step")

        if step == "model":
            tool_calls = payload.get("tool_calls", [])
            if tool_calls:
                tool_events.append({"type": "model", "tool_calls": tool_calls})
            continue

        if step == "tools":
            tool_events.append(
                {
                    "type": "tool",
                    "name": payload.get("name"),
                    "content": payload.get("content"),
                }
            )
            continue

        if step != "done":
            continue

        content = payload.get("content")
        if isinstance(content, str) and content.strip():
            final_answer = content.strip()
            return {
                "output": final_answer,
                "tool_trace": build_tool_trace_payload(
                    user_input=user_input,
                    final_answer=final_answer,
                    tool_events=tool_events,
                ),
            }

        error = payload.get("error")
        if error:
            raise ValueError(str(error))

    raise ValueError("Final response content not found in AgentService output")


def evaluation_task(dataset_item: dict[str, Any]) -> dict[str, Any]:
    user_input = dataset_item["input"]
    agent_service = AgentService()
    result = asyncio.run(run_agent_query(agent_service, user_input))

    return {
        "input": user_input,
        "output": result["output"],
        "tool_trace": result["tool_trace"],
    }


tool_correctness_judge = AgentToolCorrectnessJudge()


def score_tool_correctness(
    dataset_item: dict[str, Any], task_outputs: dict[str, Any]
) -> score_result.ScoreResult:
    transcript = task_outputs.get("tool_trace", "")
    result = tool_correctness_judge.score(output=transcript)
    result.name = "tool_correctness"
    return result


def main() -> None:
    configure_opik()
    client = Opik()
    dataset = client.get_or_create_dataset(name=DATASET_NAME)

    scoring_metrics = [
        AnswerRelevance(name="answer_relevance", require_context=False),
        ScorerWrapperMetric(score_tool_correctness, name="tool_correctness"),
        Usefulness(name="usefulness"),
    ]

    evaluate(
        dataset=dataset,
        task=evaluation_task,
        scoring_metrics=scoring_metrics,
        experiment_name=EXPERIMENT_NAME,
        project_name=settings.OPIK.PROJECT if settings.OPIK else None,
    )


if __name__ == "__main__":
    main()
