import asyncio
import json
import time
import base64
from typing import Optional, Callable, Dict, Any, List, Tuple

from loguru import logger

from vocode.streaming.agent.factory import AgentFactory
from vocode.streaming.models.audio import AudioEncoding
from vocode.streaming.models.telephony import FreeSwitchCallConfig
from vocode.streaming.synthesizer.factory import SynthesizerFactory
from vocode.streaming.telephony.conversation.abstract_phone_conversation import (
    AbstractPhoneConversation,
)
from vocode.streaming.telephony.constants import (
    FREESWITCH_AUDIO_FORMATS,
    FREESWITCH_WEBSOCKET_PING_INTERVAL,
    FREESWITCH_RECONNECT_ATTEMPTS,
    FREESWITCH_RECONNECT_DELAY,
    MULAW_SILENCE_BYTE,
    PCM_SILENCE_BYTE,
)
from vocode.streaming.transcriber.factory import TranscriberFactory
from vocode.streaming.utils.events_manager import EventsManager


class FreeSwitchPhoneConversation(AbstractPhoneConversation[FreeSwitchCallConfig]):
    def __init__(
        self,
        call_config: FreeSwitchCallConfig,
        transcriber_factory: TranscriberFactory,
        agent_factory: AgentFactory,
        synthesizer_factory: SynthesizerFactory,
        conversation_id: str,
        audio_sink: Callable[[bytes], None],
        events_manager: Optional[EventsManager] = None,
    ):
        super().__init__(
            call_config=call_config,
            transcriber_factory=transcriber_factory,
            agent_factory=agent_factory,
            synthesizer_factory=synthesizer_factory,
            conversation_id=conversation_id,
            events_manager=events_manager,
        )
        self.audio_sink = audio_sink
        self.call_start_time = time.time()
        self.call_config.call_start_time = self.call_start_time
        self.last_activity_time = self.call_start_time
        self.silence_sent = False
        self.silence_counter = 0
        self.max_silence_count = 150  # About 3 seconds of silence at 20ms chunks
        
        # Set up audio format based on config
        self.input_format = self.call_config.freeswitch_config.input_format
        self.output_format = self.call_config.freeswitch_config.output_format
        
        # Get format details
        if self.input_format in FREESWITCH_AUDIO_FORMATS:
            self.input_format_details = FREESWITCH_AUDIO_FORMATS[self.input_format]
        else:
            logger.warning(f"Unknown input format: {self.input_format}, defaulting to mulaw")
            self.input_format_details = FREESWITCH_AUDIO_FORMATS["mulaw"]
            
        if self.output_format in FREESWITCH_AUDIO_FORMATS:
            self.output_format_details = FREESWITCH_AUDIO_FORMATS[self.output_format]
        else:
            logger.warning(f"Unknown output format: {self.output_format}, defaulting to mulaw")
            self.output_format_details = FREESWITCH_AUDIO_FORMATS["mulaw"]
            
        # Set silence byte based on format
        self.silence_byte = self.output_format_details["silence_byte"]
        
        # Debugging info
        logger.info(f"FreeSwitch conversation {conversation_id} initialized with:")
        logger.info(f"  Input format: {self.input_format} ({self.input_format_details['content_type']})")
        logger.info(f"  Output format: {self.output_format} ({self.output_format_details['content_type']})")
        logger.info(f"  Sample rate: {self.call_config.freeswitch_config.sample_rate}")
        logger.info(f"  Channels: {self.call_config.freeswitch_config.channels}")

    def get_logger_tags(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.id,
            "freeswitch_call_id": self.call_config.freeswitch_call_id,
            "call_duration": int(time.time() - self.call_start_time) if self.call_start_time else 0,
        }

    def output_audio(self, chunk: bytes):
        """Send audio to the FreeSwitch call"""
        self.last_activity_time = time.time()
        self.silence_sent = False
        self.silence_counter = 0
        
        # Update call duration
        self.call_config.call_duration = int(time.time() - self.call_start_time)
        
        # Send the audio chunk
        self.audio_sink(chunk)
        
    async def send_silence(self):
        """Send silence when there's no audio to send"""
        if not self.silence_sent and self.silence_counter >= self.max_silence_count:
            # Send a chunk of silence
            silence_chunk = self.silence_byte * self.call_config.freeswitch_config.chunk_size
            self.audio_sink(silence_chunk)
            self.silence_sent = True
            self.silence_counter = 0
        else:
            self.silence_counter += 1
            
    async def handle_call_timeout(self):
        """Check if call has exceeded maximum duration"""
        if (
            self.call_config.freeswitch_config.max_call_duration and 
            time.time() - self.call_start_time > self.call_config.freeswitch_config.max_call_duration
        ):
            logger.info(f"Call {self.id} exceeded maximum duration of {self.call_config.freeswitch_config.max_call_duration}s")
            await self.terminate()
            return True
        return False
        
    async def handle_inactivity_timeout(self, timeout: int = 300):
        """Check if call has been inactive for too long"""
        if time.time() - self.last_activity_time > timeout:
            logger.info(f"Call {self.id} inactive for {timeout}s, terminating")
            await self.terminate()
            return True
        return False
        
    async def process_dtmf(self, digit: str):
        """Process DTMF tones from the call"""
        logger.info(f"Received DTMF digit: {digit} for call {self.id}")
        # You can implement custom DTMF handling here
        # For example, terminate call on # or trigger special actions
        if digit == "#":
            await self.terminate()
            
    async def terminate(self):
        """Terminate the conversation"""
        logger.info(f"Terminating FreeSwitch conversation {self.id}")
        await self.terminate_conversation()
        
    def _convert_audio_format(self, audio_data: bytes, from_format: str, to_format: str) -> bytes:
        """Convert audio between different formats if needed"""
        if from_format == to_format:
            return audio_data
            
        # This is a placeholder for actual audio conversion
        # In a real implementation, you would use a library like pydub or audioop
        logger.warning(f"Audio format conversion from {from_format} to {to_format} not implemented")
        return audio_data