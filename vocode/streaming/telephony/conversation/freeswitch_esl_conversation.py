import asyncio
from typing import Optional, Dict, Any, Callable
import threading
import queue

from loguru import logger

from vocode.streaming.agent.abstract_factory import AbstractAgentFactory
from vocode.streaming.agent.default_factory import DefaultAgentFactory
from vocode.streaming.models.agent import AgentConfig
from vocode.streaming.models.synthesizer import SynthesizerConfig
from vocode.streaming.models.telephony import FreeSwitchESLConfig, PhoneCallDirection
from vocode.streaming.models.transcriber import TranscriberConfig
from vocode.streaming.synthesizer.abstract_factory import AbstractSynthesizerFactory
from vocode.streaming.synthesizer.default_factory import DefaultSynthesizerFactory
from vocode.streaming.telephony.config_manager.base_config_manager import BaseConfigManager
from vocode.streaming.telephony.conversation.abstract_phone_conversation import (
    AbstractPhoneConversation,
)
from vocode.streaming.telephony.constants import FREESWITCH_AUDIO_ENCODING, MULAW_SILENCE_BYTE
from vocode.streaming.transcriber.abstract_factory import AbstractTranscriberFactory
from vocode.streaming.transcriber.default_factory import DefaultTranscriberFactory
from vocode.streaming.utils.events_manager import EventsManager

try:
    import ESL
except ImportError:
    logger.warning("ESL module not found. Install with 'pip install python-ESL' to use FreeSwitchESLConversation.")
    ESL = None


class FreeSwitchESLConversation(AbstractPhoneConversation):
    """
    FreeSWITCH conversation handler using direct ESL connection for audio streaming
    """
    def __init__(
        self,
        to_phone: str,
        from_phone: str,
        base_url: str,
        config_manager: BaseConfigManager,
        agent_config: AgentConfig,
        transcriber_config: TranscriberConfig,
        synthesizer_config: SynthesizerConfig,
        freeswitch_config: FreeSwitchESLConfig,
        freeswitch_uuid: str,
        conversation_id: str,
        transcriber_factory: AbstractTranscriberFactory = DefaultTranscriberFactory(),
        agent_factory: AbstractAgentFactory = DefaultAgentFactory(),
        synthesizer_factory: AbstractSynthesizerFactory = DefaultSynthesizerFactory(),
        events_manager: Optional[EventsManager] = None,
        output_to_speaker: bool = False,
        direction: PhoneCallDirection = "inbound",
    ):
        if ESL is None:
            raise ImportError("ESL module not found. Install with 'pip install python-ESL'")
            
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
        self.audio_encoding = FREESWITCH_AUDIO_ENCODING
        self.silence_byte = MULAW_SILENCE_BYTE
        
        # ESL connection
        self._esl_con = None
        self._audio_queue = queue.Queue()
        self._audio_thread = None
        self._running = False
        
    def get_telephony_config(self):
        return self.freeswitch_config
        
    async def _connect_esl(self):
        """Connect to FreeSWITCH ESL"""
        self._esl_con = ESL.ESLconnection(
            self.freeswitch_config.esl_host,
            self.freeswitch_config.esl_port,
            self.freeswitch_config.esl_password
        )
        
        if not self._esl_con.connected():
            raise ConnectionError(
                f"Failed to connect to FreeSWITCH ESL at {self.freeswitch_config.esl_host}:{self.freeswitch_config.esl_port}"
            )
            
        logger.info(f"Connected to FreeSWITCH ESL at {self.freeswitch_config.esl_host}:{self.freeswitch_config.esl_port}")
        
        # Subscribe to media bug for the call
        cmd = f"uuid_audio_start {self.freeswitch_uuid} record_session {self.conversation_id}.wav"
        e = self._esl_con.api(cmd)
        if not e or e.getBody().strip().lower() == "-err":
            raise RuntimeError(f"Failed to start audio recording: {e.getBody() if e else 'No response'}")
            
        # Subscribe to events for this call
        self._esl_con.events("plain", "all")
        
        return True
        
    def _audio_receiver_thread(self):
        """Thread to receive audio from FreeSWITCH and put it in the queue"""
        while self._running:
            if self._esl_con and self._esl_con.connected():
                e = self._esl_con.recvEvent()
                if e:
                    event_name = e.getHeader("Event-Name")
                    
                    # Handle media bug events (audio data)
                    if event_name == "CUSTOM" and e.getHeader("Event-Subclass") == "media_bug::read":
                        audio_data = e.getBody()
                        if audio_data:
                            self._audio_queue.put(audio_data)
                    
                    # Handle call hangup
                    elif event_name in ["CHANNEL_HANGUP", "CHANNEL_HANGUP_COMPLETE"]:
                        if e.getHeader("Unique-ID") == self.freeswitch_uuid:
                            logger.info(f"Call {self.freeswitch_uuid} hung up: {e.getHeader('Hangup-Cause')}")
                            self._running = False
                            break
            
            # Small sleep to prevent CPU hogging
            time.sleep(0.01)
            
    async def _send_audio_to_freeswitch(self, audio_data: bytes):
        """Send audio data to FreeSWITCH"""
        if not self._esl_con or not self._esl_con.connected():
            logger.warning("Cannot send audio: ESL connection not established")
            return False
            
        # Use displace_session to play audio to the call
        # First, we need to write the audio to a temporary file
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as temp_file:
            temp_file.write(audio_data)
            temp_path = temp_file.name
            
        try:
            # Play the file to the call
            cmd = f"uuid_displace {self.freeswitch_uuid} start {temp_path} 0 mux"
            e = self._esl_con.api(cmd)
            success = e and e.getBody().strip().lower() != "-err"
            
            if not success:
                logger.error(f"Failed to play audio: {e.getBody() if e else 'No response'}")
                
            return success
        finally:
            # Clean up the temporary file
            try:
                os.unlink(temp_path)
            except:
                pass
    
    async def attach_ws_and_start(self, websocket):
        """Start the conversation with WebSocket for signaling and ESL for audio"""
        try:
            # Connect to FreeSWITCH ESL
            await self._connect_esl()
            
            # Start the audio receiver thread
            self._running = True
            self._audio_thread = threading.Thread(target=self._audio_receiver_thread)
            self._audio_thread.daemon = True
            self._audio_thread.start()
            
            # Start the conversation
            await super().attach_ws_and_start(websocket)
            
            # Process audio from the queue
            while self._running:
                try:
                    # Get audio data with a timeout
                    audio_data = self._audio_queue.get(timeout=0.1)
                    
                    # Process the audio data (send to transcriber)
                    await self.receive_audio(audio_data)
                    
                except queue.Empty:
                    # No audio data available, just continue
                    await asyncio.sleep(0.01)
                except Exception as e:
                    logger.error(f"Error processing audio: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error in FreeSwitchESLConversation: {str(e)}")
        finally:
            # Clean up
            self._running = False
            if self._audio_thread and self._audio_thread.is_alive():
                self._audio_thread.join(timeout=2.0)
                
            if self._esl_con and self._esl_con.connected():
                # Stop the media bug
                cmd = f"uuid_audio_stop {self.freeswitch_uuid}"
                self._esl_con.api(cmd)
                self._esl_con = None
                
    async def send_audio(self, chunk):
        """Send audio to the call"""
        await self._send_audio_to_freeswitch(chunk)
        
    async def terminate(self):
        """Terminate the conversation"""
        self._running = False
        await super().terminate()