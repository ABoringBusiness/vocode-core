import asyncio
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from vocode.streaming.agent.chat_gpt_agent import ChatGPTAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchESLConfig, FreeSwitchESLCallConfig
from vocode.streaming.telephony.client.freeswitch_esl_client import FreeSwitchESLClient
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.telephony.conversation.freeswitch_esl_conversation import FreeSwitchESLConversation
from vocode.streaming.utils import create_conversation_id

load_dotenv()

# Create a FastAPI app
app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a Redis config manager
redis_host = os.getenv("REDIS_HOST", "localhost")
redis_port = int(os.getenv("REDIS_PORT", 6379))
redis_config_manager = RedisConfigManager(
    redis_host=redis_host,
    redis_port=redis_port,
)

# Create a FreeSWITCH ESL config
freeswitch_config = FreeSwitchESLConfig(
    api_url=os.getenv("FREESWITCH_API_URL", "http://localhost:8080"),
    auth_username=os.getenv("FREESWITCH_AUTH_USERNAME", "freeswitch"),
    auth_password=os.getenv("FREESWITCH_AUTH_PASSWORD", "password"),
    esl_host=os.getenv("FREESWITCH_ESL_HOST", "localhost"),
    esl_port=int(os.getenv("FREESWITCH_ESL_PORT", "8021")),
    esl_password=os.getenv("FREESWITCH_ESL_PASSWORD", "ClueCon"),
    record=True,
)

# Create a ChatGPT agent config
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm an AI assistant. How can I help you today?"),
    prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
Be concise and engaging. Ask questions when appropriate.""",
    model="gpt-3.5-turbo",
)

# WebSocket endpoint for call connections
@app.websocket("/connect_call/{conversation_id}")
async def connect_call(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    
    # Get the call config from Redis
    call_config = await redis_config_manager.get_config(conversation_id)
    if not call_config:
        await websocket.close(code=4000, reason="No active call found")
        return
    
    # Create a FreeSwitchESLConversation
    conversation = FreeSwitchESLConversation(
        to_phone=call_config.to_phone,
        from_phone=call_config.from_phone,
        base_url=os.getenv("BASE_URL", "localhost:8000"),
        config_manager=redis_config_manager,
        agent_config=call_config.agent_config,
        transcriber_config=call_config.transcriber_config,
        synthesizer_config=call_config.synthesizer_config,
        freeswitch_config=call_config.freeswitch_config,
        freeswitch_uuid=call_config.freeswitch_uuid,
        conversation_id=conversation_id,
        output_to_speaker=getattr(call_config, "output_to_speaker", False),
        direction=call_config.direction,
    )
    
    try:
        # Start the conversation
        await conversation.attach_ws_and_start(websocket)
    except WebSocketDisconnect:
        await conversation.terminate()
    except Exception as e:
        print(f"Error in conversation: {str(e)}")
        await conversation.terminate()
        await websocket.close(code=4000, reason=f"Error: {str(e)}")

# Create an endpoint to initiate an outbound call
@app.post("/outbound_call")
async def outbound_call(to_phone: str, from_phone: str, agent_id: Optional[str] = None):
    """
    Initiate an outbound call using FreeSWITCH ESL
    """
    # Create a FreeSwitchESLClient
    freeswitch_client = FreeSwitchESLClient(
        base_url=os.getenv("BASE_URL", "localhost:8000"),
        maybe_freeswitch_config=freeswitch_config,
    )

    # Create a conversation ID
    conversation_id = create_conversation_id()

    # Create a call config
    call_config = FreeSwitchESLCallConfig(
        transcriber_config=FreeSwitchESLCallConfig.default_transcriber_config(),
        agent_config=agent_config,
        synthesizer_config=FreeSwitchESLCallConfig.default_synthesizer_config(),
        freeswitch_config=freeswitch_config,
        freeswitch_uuid="",  # This will be populated by the FreeSWITCH client
        to_phone=to_phone,
        from_phone=from_phone,
        direction="outbound",
    )

    # Save the call config
    await redis_config_manager.save_config(conversation_id, call_config)

    # Initiate the call
    call_uuid = await freeswitch_client.create_call(
        conversation_id=conversation_id,
        to_phone=to_phone,
        from_phone=from_phone,
        record=True,
    )

    # Update the call config with the call UUID
    call_config.freeswitch_uuid = call_uuid
    await redis_config_manager.save_config(conversation_id, call_config)

    return {"conversation_id": conversation_id, "call_uuid": call_uuid}

# Create an endpoint to end a call
@app.post("/end_call/{conversation_id}")
async def end_call(conversation_id: str):
    """
    End a call
    """
    # Get the call config
    call_config = await redis_config_manager.get_config(conversation_id)
    if not call_config:
        return {"success": False, "error": "Call not found"}
    
    # Create a FreeSwitchESLClient
    freeswitch_client = FreeSwitchESLClient(
        base_url=os.getenv("BASE_URL", "localhost:8000"),
        maybe_freeswitch_config=freeswitch_config,
    )
    
    # End the call
    success = await freeswitch_client.end_call(call_config.freeswitch_uuid)
    
    return {"success": success, "conversation_id": conversation_id}

# Create an endpoint to handle FreeSWITCH events
@app.post("/freeswitch_event")
async def freeswitch_event(event_data: dict):
    """
    Handle FreeSWITCH events
    """
    event_name = event_data.get("Event-Name")
    call_uuid = event_data.get("Unique-ID")
    
    print(f"Received FreeSWITCH event: {event_name} for call {call_uuid}")
    
    # Handle specific events
    if event_name in ["CHANNEL_HANGUP", "CHANNEL_HANGUP_COMPLETE"]:
        # Find the conversation by call UUID
        # This would require a reverse lookup from call UUID to conversation ID
        # For now, we'll just log the event
        print(f"Call {call_uuid} hung up: {event_data.get('Hangup-Cause')}")
    
    return {"success": True}

# Create an endpoint to handle inbound calls
@app.post("/inbound_call")
async def inbound_call(call_data: dict):
    """
    Handle inbound calls from FreeSWITCH
    """
    to_phone = call_data.get("to")
    from_phone = call_data.get("from")
    call_uuid = call_data.get("uuid")
    
    if not all([to_phone, from_phone, call_uuid]):
        return {"success": False, "error": "Missing required parameters"}
    
    # Create a conversation ID
    conversation_id = create_conversation_id()
    
    # Create a call config
    call_config = FreeSwitchESLCallConfig(
        transcriber_config=FreeSwitchESLCallConfig.default_transcriber_config(),
        agent_config=agent_config,
        synthesizer_config=FreeSwitchESLCallConfig.default_synthesizer_config(),
        freeswitch_config=freeswitch_config,
        freeswitch_uuid=call_uuid,
        to_phone=to_phone,
        from_phone=from_phone,
        direction="inbound",
    )
    
    # Save the call config
    await redis_config_manager.save_config(conversation_id, call_config)
    
    # Return the WebSocket URL for FreeSWITCH to connect to
    return {
        "success": True,
        "conversation_id": conversation_id,
        "websocket_url": f"ws://{os.getenv('BASE_URL', 'localhost:8000')}/connect_call/{conversation_id}"
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)