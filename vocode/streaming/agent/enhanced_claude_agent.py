import os
import random
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import sentry_sdk
from anthropic import AsyncAnthropic, AsyncStream
from anthropic.types import MessageStreamEvent
from loguru import logger

from vocode.streaming.action.abstract_factory import AbstractActionFactory
from vocode.streaming.action.default_factory import DefaultActionFactory
from vocode.streaming.agent.anthropic_utils import format_anthropic_chat_messages_from_transcript
from vocode.streaming.agent.base_agent import GeneratedResponse, RespondAgent, StreamedResponse
from vocode.streaming.agent.streaming_utils import collate_response_async, stream_response_async
from vocode.streaming.models.actions import FunctionFragment
from vocode.streaming.models.agent import EnhancedClaudeAgentConfig
from vocode.streaming.models.message import BaseMessage, BotBackchannel, LLMToken
from vocode.streaming.vector_db.factory import VectorDBFactory
from vocode.utils.sentry_utils import CustomSentrySpans, sentry_create_span


class EnhancedClaudeAgent(RespondAgent[EnhancedClaudeAgentConfig]):
    anthropic_client: AsyncAnthropic

    def __init__(
        self,
        agent_config: EnhancedClaudeAgentConfig,
        action_factory: AbstractActionFactory = DefaultActionFactory(),
        vector_db_factory=VectorDBFactory(),
        **kwargs,
    ):
        super().__init__(
            agent_config=agent_config,
            action_factory=action_factory,
            **kwargs,
        )
        
        # Initialize Anthropic client with appropriate configuration
        api_key = agent_config.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Anthropic API key must be provided in agent_config or as an environment variable")
        
        client_kwargs = {
            "api_key": api_key,
        }
        
        # Add base URL override if provided
        if agent_config.base_url_override:
            client_kwargs["base_url"] = agent_config.base_url_override
            
        # Add timeout configuration
        if agent_config.request_timeout:
            client_kwargs["timeout"] = agent_config.request_timeout
            
        # Initialize the client
        self.anthropic_client = AsyncAnthropic(**client_kwargs)
        
        # Initialize vector DB if configured
        if self.agent_config.vector_db_config:
            self.vector_db = vector_db_factory.create_vector_db(self.agent_config.vector_db_config)

    def get_chat_parameters(self, messages: list = [], use_functions: bool = True):
        assert self.transcript is not None

        parameters: dict[str, Any] = {
            "messages": messages,
            "system": self.agent_config.prompt_preamble,
            "max_tokens": self.agent_config.max_tokens,
            "temperature": self.agent_config.temperature,
            "stream": True,
        }

        parameters["model"] = self.agent_config.model_name
        
        # Add top_p if specified
        if self.agent_config.top_p is not None:
            parameters["top_p"] = self.agent_config.top_p
            
        # Add top_k if specified
        if self.agent_config.top_k is not None:
            parameters["top_k"] = self.agent_config.top_k
            
        # Add stop sequences if specified
        if self.agent_config.stop_sequences:
            parameters["stop_sequences"] = self.agent_config.stop_sequences

        return parameters

    async def token_generator(
        self,
        gen: AsyncStream[MessageStreamEvent],
    ) -> AsyncGenerator[str | FunctionFragment, None]:
        async for chunk in gen:
            if chunk.type == "content_block_delta" and chunk.delta.type == "text_delta":
                yield chunk.delta.text

    async def _get_anthropic_stream(self, chat_parameters: Dict[str, Any]):
        try:
            return await self.anthropic_client.messages.create(**chat_parameters)
        except Exception as e:
            logger.error(
                f"Error while hitting Anthropic with chat_parameters: {chat_parameters}",
                exc_info=True,
            )
            raise e

    def should_backchannel(self, human_input: str) -> bool:
        return (
            self.agent_config.use_backchannels
            and not self.is_first_response()
            and not human_input.strip().endswith("?")
            and random.random() < self.agent_config.backchannel_probability
        )

    def choose_backchannel(self) -> Optional[BotBackchannel]:
        backchannel = None
        if self.transcript is not None:
            last_bot_message = None
            for event_log in self.transcript.event_logs[::-1]:
                if hasattr(event_log, "sender") and event_log.sender == "BOT":
                    last_bot_message = event_log
                    break
            if last_bot_message and last_bot_message.text.strip().endswith("?"):
                return BotBackchannel(text=self.post_question_bot_backchannel_randomizer())
        return backchannel

    async def generate_response(
        self,
        human_input,
        conversation_id: str,
        is_interrupt: bool = False,
        bot_was_in_medias_res: bool = False,
    ) -> AsyncGenerator[GeneratedResponse, None]:
        if not self.transcript:
            raise ValueError("A transcript is not attached to the agent")
            
        messages = format_anthropic_chat_messages_from_transcript(transcript=self.transcript)
        
        # Add vector DB context if configured
        if self.agent_config.vector_db_config:
            try:
                docs_with_scores = await self.vector_db.similarity_search_with_score(
                    self.transcript.get_last_user_message()[1]
                )
                docs_with_scores_str = "\n\n".join(
                    [
                        "Document: "
                        + doc[0].metadata["source"]
                        + f" (Confidence: {doc[1]})\n"
                        + doc[0].lc_kwargs["page_content"].replace(r"\n", "\n")
                        for doc in docs_with_scores
                    ]
                )
                vector_db_result = (
                    f"Found {len(docs_with_scores)} similar documents:\n{docs_with_scores_str}"
                )
                # Add vector DB results to the last user message
                last_message_content = messages[-2]["content"]
                messages[-2]["content"] = f"{last_message_content}\n\nReference Information: {vector_db_result}"
            except Exception as e:
                logger.error(f"Error while hitting vector db: {e}", exc_info=True)
        
        chat_parameters = self.get_chat_parameters(messages)
        
        # Handle backchannels
        backchannelled = "false"
        backchannel: Optional[BotBackchannel] = None
        if (
            self.agent_config.use_backchannels
            and not bot_was_in_medias_res
            and self.should_backchannel(human_input)
        ):
            backchannel = self.choose_backchannel()
        elif self.agent_config.first_response_filler_message and self.is_first_response():
            backchannel = BotBackchannel(text=self.agent_config.first_response_filler_message)

        if backchannel is not None:
            # Add backchannel to the transcript
            yield GeneratedResponse(
                message=backchannel,
                is_interruptible=True,
            )
            backchannelled = "true"

        first_sentence_total_span = sentry_create_span(
            sentry_callable=sentry_sdk.start_span, op=CustomSentrySpans.LLM_FIRST_SENTENCE_TOTAL
        )

        ttft_span = sentry_create_span(
            sentry_callable=sentry_sdk.start_span, op=CustomSentrySpans.TIME_TO_FIRST_TOKEN
        )
        
        stream = await self._get_anthropic_stream(chat_parameters)

        response_generator = collate_response_async
        using_input_streaming_synthesizer = (
            self.conversation_state_manager.using_input_streaming_synthesizer()
        )
        if using_input_streaming_synthesizer:
            response_generator = stream_response_async
            
        async for message in response_generator(
            conversation_id=conversation_id,
            gen=self.token_generator(
                stream,
            ),
            sentry_span=ttft_span,
        ):
            if first_sentence_total_span:
                first_sentence_total_span.finish()

            ResponseClass = (
                StreamedResponse if using_input_streaming_synthesizer else GeneratedResponse
            )
            MessageType = LLMToken if using_input_streaming_synthesizer else BaseMessage

            if isinstance(message, str):
                yield ResponseClass(
                    message=MessageType(text=message),
                    is_interruptible=True,
                )
            else:
                yield ResponseClass(
                    message=message,
                    is_interruptible=True,
                )