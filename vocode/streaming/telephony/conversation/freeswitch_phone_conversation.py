import asyncio
import base64
import json
from typing import Optional

import ESL
from fastapi import WebSocket
from loguru import logger

from vocode.streaming.agent.abstract_factory import AbstractAgentFactory
from vocode.streaming.agent.default_factory import DefaultAgentFactory
from vocode.streaming.models.agent import AgentConfig
from vocode.streaming.models.synthesizer import SynthesizerConfig
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.models.transcriber import TranscriberConfig
from vocode.streaming.synthesizer.abstract_factory import AbstractSynthesizerFactory
from vocode.streaming.synthesizer.default_factory import DefaultSynthesizerFactory
from vocode.streaming.telephony.config_manager.base_config_manager import BaseConfigManager
from vocode.streaming.telephony.constants import (
    FREESWITCH_AUDIO_ENCODING,
    FREESWITCH_CHUNK_SIZE,
    FREESWITCH_SAMPLING_RATE,
    MULAW_SILENCE_BYTE,
)
from vocode.streaming.telephony.conversation.abstract_phone_conversation import (
    AbstractPhoneConversation,
)
from vocode.streaming.transcriber.abstract_factory import AbstractTranscriberFactory
from vocode.streaming.transcriber.default_factory import DefaultTranscriberFactory
from vocode.streaming.utils.events_manager import EventsManager


class FreeSwitchPhoneConversation(AbstractPhoneConversation):
    def __init__(
        self,
        to_phone: str,
        from_phone: str,
        base_url: str,
        config_manager: BaseConfigManager,
        agent_config: AgentConfig,
        transcriber_config: TranscriberConfig,
        synthesizer_config: SynthesizerConfig,
        freeswitch_config: FreeSwitchConfig,
        freeswitch_uuid: str,
        conversation_id: str,
        transcriber_factory: AbstractTranscriberFactory = DefaultTranscriberFactory(),
        agent_factory: AbstractAgentFactory = DefaultAgentFactory(),
        synthesizer_factory: AbstractSynthesizerFactory = DefaultSynthesizerFactory(),
        events_manager: Optional[EventsManager] = None,
        output_to_speaker: bool = False,
        direction: str = "outbound",
    ):
        super().__init__(
            to_phone=to_phone,
            from_phone=from_phone,
            base_url=base_url,
            config_manager=config_manager,
            agent_config=agent_config,
            transcriber_config=transcriber_config,
            synthesizer_config=synthesizer_config,
            conversation_id=conversation_id,
            transcriber_factory=transcriber_factory,
            agent_factory=agent_factory,
            synthesizer_factory=synthesizer_factory,
            events_manager=events_manager,
            direction=direction,
        )
        self.freeswitch_config = freeswitch_config
        self.freeswitch_uuid = freeswitch_uuid
        self.output_to_speaker = output_to_speaker
        self.esl_connection = None

    async def attach_ws_and_start(self, websocket: WebSocket):
        """Attach a WebSocket and start the conversation

        Args:
            websocket: The WebSocket to attach
        """
        await super().attach_ws_and_start(websocket)
        
        # Start the ESL connection for sending audio back to FreeSWITCH
        if self.freeswitch_config:
            try:
                # Connect to FreeSWITCH ESL
                self.esl_connection = ESL.ESLconnection(
                    self.freeswitch_config.host, 
                    self.freeswitch_config.port, 
                    self.freeswitch_config.password
                )
                
                if not self.esl_connection.connected():
                    logger.error(f"Failed to connect to FreeSWITCH at {self.freeswitch_config.host}:{self.freeswitch_config.port}")
            except Exception as e:
                logger.error(f"Error connecting to FreeSWITCH ESL: {e}")

    async def receive_audio(self, chunk: bytes):
        """Receive audio from the WebSocket and send it to the transcriber

        Args:
            chunk: The audio chunk to process
        """
        await self.transcriber.send_audio(chunk)

    async def send_audio(self, chunk: bytes):
        """Send audio to the WebSocket and to FreeSWITCH via ESL

        Args:
            chunk: The audio chunk to send
        """
        if self.websocket:
            await self.websocket.send_bytes(chunk)
        
        # Send audio to FreeSWITCH via ESL if connected
        if self.esl_connection and self.esl_connection.connected():
            try:
                # Encode the audio chunk for transmission
                encoded_chunk = base64.b64encode(chunk).decode('utf-8')
                
                # Send the audio to the call via ESL
                cmd = f"uuid_send_media {self.freeswitch_uuid} {encoded_chunk}"
                self.esl_connection.api(cmd)
            except Exception as e:
                logger.error(f"Error sending audio to FreeSWITCH: {e}")

    def get_silence_chunk(self) -> bytes:
        """Get a chunk of silence

        Returns:
            A chunk of silence in the appropriate format
        """
        return MULAW_SILENCE_BYTE * FREESWITCH_CHUNK_SIZE

    async def terminate(self):
        """Terminate the conversation and clean up resources"""
        await super().terminate()
        
        # Close the ESL connection if it exists
        if self.esl_connection and self.esl_connection.connected():
            self.esl_connection.disconnect()
            self.esl_connection = None