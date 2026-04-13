import traceback
from typing import Any, AsyncGenerator, Union

from a2a_servers.common.server import utils
from a2a_servers.common.server.task_manager import InMemoryTaskManager
from a2a_servers.common.types import (
    SendTaskRequest,
    TaskSendParams,
    Message,
    TaskStatus,
    Artifact,
    TaskStatusUpdateEvent,
    TaskArtifactUpdateEvent,
    TextPart,
    TaskState,
    Task,
    SendTaskResponse,
    InternalError,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
)
import json
from typing import AsyncIterable


class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, agent: Any):
        super().__init__()
        self.agent = agent

    async def _stream_generator(
        self, request: SendTaskStreamingRequest
    ) -> AsyncGenerator[SendTaskStreamingResponse | JSONRPCResponse, Any]:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
          async for item in self.agent.stream(query, task_send_params.sessionId):
            is_task_complete = item["is_task_complete"]
            artifacts = None
            if not is_task_complete:
              task_state = TaskState.WORKING
              parts = [{"type": "text", "text": item["updates"]}]
            else:
              if isinstance(item["content"], dict):
                if ("response" in item["content"]
                    and "result" in item["content"]["response"]):
                  data = json.loads(item["content"]["response"]["result"])
                  task_state = TaskState.INPUT_REQUIRED
                else:
                  data = item["content"]
                  task_state = TaskState.COMPLETED
                parts = [{"type": "data", "data": data}]
              else:
                task_state = TaskState.COMPLETED
                parts = [{"type": "text", "text": item["content"]}]
              artifacts = [Artifact(parts=parts, index=0, append=False)]
          message = Message(role="agent", parts=parts)
          task_status = TaskStatus(state=task_state, message=message)
          await self._update_store(task_send_params.id, task_status, artifacts)
          task_update_event = TaskStatusUpdateEvent(
                id=task_send_params.id,
                status=task_status,
                final=False,
            )
          yield SendTaskStreamingResponse(id=request.id, result=task_update_event)
          if artifacts:
            for artifact in artifacts:
              yield SendTaskStreamingResponse(
                  id=request.id,
                  result=TaskArtifactUpdateEvent(
                      id=task_send_params.id,
                      artifact=artifact,
                  )
              )
          if is_task_complete:
            yield SendTaskStreamingResponse(
              id=request.id,
              result=TaskStatusUpdateEvent(
                  id=task_send_params.id,
                  status=TaskStatus(
                      state=task_status.state,
                  ),
                  final=True
              )
            )
        except Exception as e:
            yield JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message="An error occurred while streaming the response"
                ),
            )
    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ):
        task_send_params: TaskSendParams = request.params
        if not utils.are_modalities_compatible(
            task_send_params.acceptedOutputModes, self.agent.SUPPORTED_CONTENT_TYPES
        ):
            return utils.new_incompatible_types_error(request.id)
    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        error = self._validate_request(request)
        if error:
            return error
        await self.upsert_task(request.params)
        return await self._invoke(request)
    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        error = self._validate_request(request)
        if error:
            return error
        await self.upsert_task(request.params)
        return self._stream_generator(request)
    async def _update_store(
        self, task_id: str, status: TaskStatus, artifacts: list[Artifact]
    ) -> Task:
        async with self.lock:
            try:
                task = self.tasks[task_id]
            except KeyError:
                raise ValueError(f"Task {task_id} not found")
            task.status = status
            if artifacts is not None:
                if task.artifacts is None:
                    task.artifacts = []
                task.artifacts.extend(artifacts)
            return task

    async def _invoke(self, request: SendTaskRequest) -> SendTaskResponse:
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        import asyncio as _asyncio
        import logging as _logging
        _log = _logging.getLogger(__name__)
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                result = await self.agent.invoke(query, task_send_params.sessionId)
                break
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                retryable = any(kw in err_str for kw in [
                    "tool_use_failed", "bad request", "400",
                    "rate_limit", "rate limit", "429", "try again",
                ])
                if attempt < max_retries - 1 and retryable:
                    wait = 5 * (attempt + 1)
                    _log.warning(f"Retrying in {wait}s (attempt {attempt + 1}/{max_retries}): {e}")
                    await _asyncio.sleep(wait)
                    continue
                raise ValueError(f"Error invoking agent: {e}")
        else:
            raise ValueError(f"Error invoking agent after {max_retries} retries: {last_error}")

        # OpenAI requires the result to be a string inside the part
        if not isinstance(result, str):
            result_str = json.dumps(result)
        else:
            result_str = result

        # We must ensure the 'role' is consistent with what the model expects
        # By default, ADK uses 'agent' or 'model'. 
        # For OpenAI via LiteLLM, a tool result needs to be returned as a Tool part.
        parts = [{"type": "text", "text": result_str}]
        
        # Determine state
        task_state = TaskState.INPUT_REQUIRED if "MISSING_INFO:" in result_str else TaskState.COMPLETED
        
        task = await self._update_store(
            task_send_params.id,
            TaskStatus(
                state=task_state, 
                message=Message(role="agent", parts=parts)
            ),
            [Artifact(parts=parts)],
        )
        return SendTaskResponse(id=request.id, result=task)
    # async def _invoke(self, request: SendTaskRequest) -> SendTaskResponse:
    #     task_send_params: TaskSendParams = request.params
    #     query = self._get_user_query(task_send_params)
    #     try:
    #         result = await self.agent.invoke(query, task_send_params.sessionId)
    #     except Exception as e:
    #         raise ValueError(f"Error invoking agent: {e}")
    #     parts = [{"type": "text", "text": result}]
    #     task_state = TaskState.INPUT_REQUIRED if "MISSING_INFO:" in result else TaskState.COMPLETED
    #     task = await self._update_store(
    #         task_send_params.id,
    #         TaskStatus(
    #             state=task_state, message=Message(role="agent", parts=parts)
    #         ),
    #         [Artifact(parts=parts)],
    #     )
    #     return SendTaskResponse(id=request.id, result=task)

    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        part = task_send_params.message.parts[0]
        return part.text
