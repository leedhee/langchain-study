import asyncio
import contextlib
from datetime import datetime
import json
import os
import uuid

from app.utils.logger import log_execution, custom_logger
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.checkpoint.memory import InMemorySaver
from app.agents.medical_agent import create_medical_agent
from opik.integrations.langchain import OpikTracer, track_langgraph
from app.core.config import settings


# Opik 설정 준비
def configure_opik():
    opik_settings = settings.OPIK
    if not opik_settings:
        return None

    if opik_settings.URL_OVERRIDE:
        os.environ["OPIK_URL_OVERRIDE"] = opik_settings.URL_OVERRIDE
    if opik_settings.API_KEY:
        os.environ["OPIK_API_KEY"] = opik_settings.API_KEY
    if opik_settings.WORKSPACE:
        os.environ["OPIK_WORKSPACE"] = opik_settings.WORKSPACE
    if not opik_settings.PROJECT:
        custom_logger.warning("Opik disabled: project is empty")
        return None

    return {
        "project_name": opik_settings.PROJECT,
        "metadata": {"service": "agent-service"},
        "tags": ["medical-agent"],
    }


class AgentService:
    def __init__(self):
        self.agent = None
        self.opik_config = configure_opik()
        self.opik_tracer = None
        self.progress_queue: asyncio.Queue = asyncio.Queue()
        self.checkpointer = self._init_checkpointer()

    def _init_checkpointer(self):
        return InMemorySaver()

    def _create_agent(self):
        """LangChain 에이전트 생성"""
        if self.agent is None:
            agent = create_medical_agent(checkpointer=self.checkpointer)
            if self.opik_config is not None:
                self.opik_tracer = OpikTracer(
                    project_name=self.opik_config["project_name"],
                    metadata=self.opik_config["metadata"],
                    tags=self.opik_config["tags"],
                )
                agent = track_langgraph(agent, self.opik_tracer)
            self.agent = agent

    @log_execution
    async def process_query(self, user_messages: str, thread_id: uuid.UUID):
        """LangChain Messages 형식의 쿼리를 처리하고 AIMessage 형식으로 반환합니다."""
        try:
            self._create_agent()

            custom_logger.info(f"AgentService in process_query: {id(self)}")
            custom_logger.info(f"Checkpointer in process_query: {id(self.checkpointer)}")
            custom_logger.info(f"쓰레드 아이디: {thread_id}")
            custom_logger.info(f"사용자 메시지: {user_messages}")

            agent_stream = self.agent.astream(
                {"messages": [HumanMessage(content=user_messages)]},
                config={"configurable": {"thread_id": str(thread_id)}},
                stream_mode="updates",
            )

            agent_iterator = agent_stream.__aiter__()
            agent_task = asyncio.create_task(agent_iterator.__anext__())
            progress_task = asyncio.create_task(self.progress_queue.get())

            while True:
                pending = {agent_task}
                if progress_task is not None:
                    pending.add(progress_task)

                done, _ = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)

                if progress_task in done:
                    try:
                        progress_event = progress_task.result()
                        yield json.dumps(progress_event, ensure_ascii=False)
                        progress_task = asyncio.create_task(self.progress_queue.get())
                    except asyncio.CancelledError:
                        progress_task = None
                    except Exception as e:
                        custom_logger.error(f"Error in progress_task: {e}")
                        progress_task = None

                if agent_task in done:
                    try:
                        chunk = agent_task.result()
                    except StopAsyncIteration:
                        agent_task = None
                        break
                    except Exception as e:
                        custom_logger.error(f"Error in agent_task: {e}")
                        import traceback
                        custom_logger.error(traceback.format_exc())
                        agent_task = None

                        error_response = {
                            "step": "done",
                            "message_id": str(uuid.uuid4()),
                            "role": "assistant",
                            "content": "처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                            "metadata": {},
                            "created_at": datetime.utcnow().isoformat(),
                            "error": str(e),
                        }
                        yield json.dumps(error_response, ensure_ascii=False)
                        break

                    custom_logger.info(f"에이전트 청크: {chunk}")

                    try:
                        for step, event in chunk.items():
                            allowed_steps = ["model", "tools"]
                            if not event or step not in allowed_steps:
                                continue

                            messages = event.get("messages", [])
                            if len(messages) == 0:
                                continue
                            message = messages[0]

                            if step == "model":
                                tool_calls = getattr(message, "tool_calls", None) or []

                                if not tool_calls:
                                    content = getattr(message, "content", None)
                                    if content:
                                        yield json.dumps(
                                            {
                                                "step": "done",
                                                "message_id": str(uuid.uuid4()),
                                                "role": "assistant",
                                                "content": content,
                                                "metadata": {},
                                                "created_at": datetime.utcnow().isoformat(),
                                            },
                                            ensure_ascii=False,
                                        )
                                    continue

                                tool = tool_calls[0]
                                if tool.get("name") == "AgentResponse":
                                    args = tool.get("args", {})
                                    metadata = args.get("metadata")
                                    yield json.dumps(
                                        {
                                            "step": "done",
                                            "message_id": args.get("message_id"),
                                            "role": "assistant",
                                            "content": args.get("content"),
                                            "metadata": self._handle_metadata(metadata),
                                            "created_at": datetime.utcnow().isoformat(),
                                        },
                                        ensure_ascii=False,
                                    )
                                else:
                                    yield json.dumps(
                                        {
                                            "step": "model",
                                            "tool_calls": [tool["name"] for tool in tool_calls],
                                        },
                                        ensure_ascii=False,
                                    )

                            if step == "tools":
                                yield json.dumps(
                                    {
                                        "step": "tools",
                                        "name": message.name,
                                        "content": message.content,
                                    },
                                    ensure_ascii=False,
                                )

                    except Exception as e:
                        custom_logger.error(f"Error processing chunk: {e}")
                        import traceback
                        custom_logger.error(traceback.format_exc())

                        error_response = {
                            "step": "done",
                            "message_id": str(uuid.uuid4()),
                            "role": "assistant",
                            "content": "데이터 처리 중 오류가 발생했습니다.",
                            "metadata": {},
                            "created_at": datetime.utcnow().isoformat(),
                            "error": str(e),
                        }
                        yield json.dumps(error_response, ensure_ascii=False)
                        break

                    agent_task = asyncio.create_task(agent_iterator.__anext__())

            if progress_task is not None:
                progress_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await progress_task

            while not self.progress_queue.empty():
                try:
                    remaining = self.progress_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                yield json.dumps(remaining, ensure_ascii=False)

        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            custom_logger.error(f"Error in process_query: {e}")
            custom_logger.error(error_trace)

            error_response = {
                "step": "done",
                "message_id": str(uuid.uuid4()),
                "role": "assistant",
                "content": "처리 중 오류가 발생했습니다. 다시 시도해주세요.",
                "metadata": {},
                "created_at": datetime.utcnow().isoformat(),
                "error": str(e) if not isinstance(e, GraphRecursionError) else None,
            }
            yield json.dumps(error_response, ensure_ascii=False)

    @log_execution
    def _handle_metadata(self, metadata) -> dict:
        custom_logger.info("========================================")
        custom_logger.info(metadata)
        result = {}
        if metadata:
            for k, v in metadata.items():
                result[k] = v
        return result
