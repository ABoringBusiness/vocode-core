import asyncio
import base64
import json
import time
import uuid
from typing import Dict, Optional, Tuple, cast, List, Any

from fastapi import APIRouter, Depends, Header, Request, Response, WebSocket, WebSocketDisconnect
from loguru import logger
from starlette.websockets import WebSocketDisconnect

from vocode.streaming.models.audio import AudioEncoding
from vocode.streaming.models.telephony import FreeSwitchCallConfig
from vocode.streaming.telephony.constants import (
    FREESWITCH_AUDIO_ENCODING,
    FREESWITCH_CHUNK_SIZE,
    FREESWITCH_CONTENT_TYPE,
    FREESWITCH_SAMPLING_RATE,
    FREESWITCH_AUDIO_FORMATS,
    FREESWITCH_WEBSOCKET_PING_INTERVAL,
    FREESWITCH_RECONNECT_ATTEMPTS,
    FREESWITCH_RECONNECT_DELAY,
    MULAW_SILENCE_BYTE,
)
from vocode.streaming.telephony.conversation import TelephonyConversation
from vocode.streaming.telephony.conversation.freeswitch_phone_conversation import FreeSwitchPhoneConversation
from vocode.streaming.telephony.server.base import TelephonyServer


class FreeSwitchHandler:
    def __init__(
        self,
        telephony_server: TelephonyServer,
        router: APIRouter,
        conversation_id_to_call_sid: Dict[str, str],
        call_sid_to_conversation_id: Dict[str, str],
    ):
        self.telephony_server = telephony_server
        self.router = router
        self.conversation_id_to_call_sid = conversation_id_to_call_sid
        self.call_sid_to_conversation_id = call_sid_to_conversation_id
        self.active_websockets: Dict[str, WebSocket] = {}
        self.active_conversations: Dict[str, FreeSwitchPhoneConversation] = {}
        self.call_metadata: Dict[str, Dict[str, Any]] = {}
        self.setup_routes()
        
        # Start background tasks
        self.ping_task = asyncio.create_task(self._ping_websockets())
        self.cleanup_task = asyncio.create_task(self._cleanup_inactive_calls())

    def setup_routes(self):
        @self.router.post("/calls/{conversation_id}/events")
        async def handle_freeswitch_event(conversation_id: str, request: Request):
            """Handle FreeSwitch call events (hangup, dtmf, etc.)"""
            try:
                event_data = await request.json()
                event_type = event_data.get("event")
                call_id = event_data.get("call_id")
                
                logger.info(f"Received FreeSwitch event: {event_type} for call {call_id}")
                
                # Store call metadata
                if call_id and call_id not in self.call_metadata:
                    self.call_metadata[call_id] = {}
                
                if call_id:
                    self.call_metadata[call_id].update({
                        "last_event": event_type,
                        "last_event_time": time.time(),
                        "event_count": self.call_metadata.get(call_id, {}).get("event_count", 0) + 1,
                    })
                
                # Handle different event types
                if event_type == "hangup":
                    # Handle call hangup
                    if conversation_id in self.conversation_id_to_call_sid:
                        await self.telephony_server.end_conversation(conversation_id)
                        if self.conversation_id_to_call_sid[conversation_id] in self.call_sid_to_conversation_id:
                            del self.call_sid_to_conversation_id[self.conversation_id_to_call_sid[conversation_id]]
                        del self.conversation_id_to_call_sid[conversation_id]
                        logger.info(f"Ended conversation {conversation_id} due to hangup")
                        
                        # Clean up resources
                        if conversation_id in self.active_conversations:
                            del self.active_conversations[conversation_id]
                
                elif event_type == "dtmf":
                    # Handle DTMF events
                    digit = event_data.get("digit")
                    if digit and conversation_id in self.active_conversations:
                        await self.active_conversations[conversation_id].process_dtmf(digit)
                
                elif event_type == "answer":
                    # Handle call answer event
                    if call_id and conversation_id not in self.conversation_id_to_call_sid:
                        self.conversation_id_to_call_sid[conversation_id] = call_id
                        self.call_sid_to_conversation_id[call_id] = conversation_id
                        logger.info(f"Call {call_id} answered and mapped to conversation {conversation_id}")
                
                elif event_type == "ringing":
                    # Handle call ringing event
                    logger.info(f"Call {call_id} is ringing")
                
                elif event_type == "bridge":
                    # Handle call bridge event
                    logger.info(f"Call {call_id} bridged")
                    
                # Return success response
                return Response(
                    content=json.dumps({"success": True}),
                    media_type="application/json",
                    status_code=200
                )
            except Exception as e:
                logger.error(f"Error handling FreeSwitch event: {e}")
                return Response(
                    content=json.dumps({"success": False, "error": str(e)}),
                    media_type="application/json",
                    status_code=500
                )

        @self.router.websocket("/calls/{conversation_id}/stream")
        async def handle_freeswitch_stream(websocket: WebSocket, conversation_id: str):
            """Handle WebSocket connection for audio streaming with FreeSwitch"""
            await websocket.accept()
            logger.info(f"FreeSwitch WebSocket connected for conversation {conversation_id}")
            
            # Store the websocket for this conversation
            self.active_websockets[conversation_id] = websocket
            
            try:
                # Get or create the conversation
                conversation = await self.get_or_create_conversation(conversation_id, websocket)
                
                # Store the conversation
                self.active_conversations[conversation_id] = conversation
                
                # Start the conversation
                if not conversation.is_active():
                    await conversation.start()
                
                # Process incoming audio from FreeSwitch
                while True:
                    message = await websocket.receive_text()
                    data = json.loads(message)
                    
                    if data["type"] == "audio":
                        # Decode base64 audio and send to conversation
                        audio_data = base64.b64decode(data["data"])
                        await conversation.receive_audio(audio_data)
                    elif data["type"] == "dtmf":
                        # Handle DTMF message
                        await conversation.process_dtmf(data["digit"])
                    elif data["type"] == "hangup":
                        # Handle hangup message
                        logger.info(f"Received hangup via WebSocket for conversation {conversation_id}")
                        await self.telephony_server.end_conversation(conversation_id)
                        break
                    elif data["type"] == "ping":
                        # Handle ping message
                        await websocket.send_text(json.dumps({"type": "pong"}))
            
            except WebSocketDisconnect:
                logger.info(f"FreeSwitch WebSocket disconnected for conversation {conversation_id}")
                await self.telephony_server.end_conversation(conversation_id)
            except Exception as e:
                logger.error(f"Error in FreeSwitch WebSocket handler: {e}")
                await self.telephony_server.end_conversation(conversation_id)
            finally:
                if conversation_id in self.active_websockets:
                    del self.active_websockets[conversation_id]
                if conversation_id in self.active_conversations:
                    del self.active_conversations[conversation_id]

    async def get_or_create_conversation(
        self, conversation_id: str, websocket: WebSocket
    ) -> FreeSwitchPhoneConversation:
        """Get an existing conversation or create a new one"""
        if conversation_id in self.telephony_server.conversations:
            return cast(FreeSwitchPhoneConversation, self.telephony_server.conversations[conversation_id])
        
        # Create a new conversation
        call_config = await self.create_call_config(conversation_id)
        
        # Create the conversation with the call config
        conversation = await self.create_conversation(
            call_config=call_config,
            conversation_id=conversation_id,
            audio_sink=self.create_audio_sink(conversation_id, websocket),
        )
        
        return conversation

    async def create_call_config(self, conversation_id: str) -> FreeSwitchCallConfig:
        """Create a call config for the conversation"""
        # Get the call ID from the conversation ID mapping
        call_id = self.conversation_id_to_call_sid.get(conversation_id, f"fs-{uuid.uuid4()}")
        
        # If not in mapping, add it
        if conversation_id not in self.conversation_id_to_call_sid:
            self.conversation_id_to_call_sid[conversation_id] = call_id
            self.call_sid_to_conversation_id[call_id] = conversation_id
        
        # Create a basic FreeSwitch call config
        call_config = FreeSwitchCallConfig(
            transcriber_config=FreeSwitchCallConfig.default_transcriber_config(),
            agent_config=self.telephony_server.default_agent_config,
            synthesizer_config=FreeSwitchCallConfig.default_synthesizer_config(),
            from_phone="unknown",  # Would be populated from actual call data
            to_phone="unknown",    # Would be populated from actual call data
            freeswitch_config=self.telephony_server.telephony_config,
            freeswitch_call_id=call_id,
            direction="inbound",   # Assuming inbound call for now
            stream_id=str(uuid.uuid4()),  # Generate a unique stream ID
        )
        
        return call_config

    async def create_conversation(
        self, call_config: FreeSwitchCallConfig, conversation_id: str, audio_sink: Callable[[bytes], None]
    ) -> FreeSwitchPhoneConversation:
        """Create a new FreeSwitch conversation"""
        conversation = FreeSwitchPhoneConversation(
            call_config=call_config,
            transcriber_factory=self.telephony_server.transcriber_factory,
            agent_factory=self.telephony_server.agent_factory,
            synthesizer_factory=self.telephony_server.synthesizer_factory,
            conversation_id=conversation_id,
            audio_sink=audio_sink,
            events_manager=self.telephony_server.events_manager,
        )
        
        # Store the conversation
        self.telephony_server.conversations[conversation_id] = conversation
        
        return conversation

    def create_audio_sink(self, conversation_id: str, websocket: WebSocket):
        """Create an audio sink function that sends audio to the FreeSwitch WebSocket"""
        
        async def audio_sink(audio_chunk: bytes):
            if conversation_id in self.active_websockets:
                try:
                    # Send audio data as base64-encoded string in a JSON message
                    await websocket.send_text(
                        json.dumps({
                            "type": "audio",
                            "data": base64.b64encode(audio_chunk).decode("utf-8")
                        })
                    )
                except Exception as e:
                    logger.error(f"Error sending audio to FreeSwitch: {e}")
        
        return audio_sink
        
    async def _ping_websockets(self):
        """Send periodic ping messages to keep WebSockets alive"""
        while True:
            try:
                for conversation_id, websocket in list(self.active_websockets.items()):
                    try:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                    except Exception as e:
                        logger.warning(f"Error sending ping to WebSocket for conversation {conversation_id}: {e}")
                        # Don't remove here, let the main handler handle disconnections
            except Exception as e:
                logger.error(f"Error in WebSocket ping task: {e}")
            
            await asyncio.sleep(FREESWITCH_WEBSOCKET_PING_INTERVAL)
            
    async def _cleanup_inactive_calls(self):
        """Clean up inactive calls and resources"""
        while True:
            try:
                # Check for inactive calls
                current_time = time.time()
                for call_id, metadata in list(self.call_metadata.items()):
                    last_event_time = metadata.get("last_event_time", 0)
                    if current_time - last_event_time > 3600:  # 1 hour
                        # Call is inactive for too long, clean up
                        if call_id in self.call_sid_to_conversation_id:
                            conversation_id = self.call_sid_to_conversation_id[call_id]
                            if conversation_id in self.conversation_id_to_call_sid:
                                del self.conversation_id_to_call_sid[conversation_id]
                            del self.call_sid_to_conversation_id[call_id]
                            
                            # End the conversation if it exists
                            if conversation_id in self.telephony_server.conversations:
                                await self.telephony_server.end_conversation(conversation_id)
                                
                        # Remove metadata
                        del self.call_metadata[call_id]
                        logger.info(f"Cleaned up inactive call {call_id}")
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                
            await asyncio.sleep(300)  # Run every 5 minutes