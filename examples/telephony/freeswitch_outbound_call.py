#!/usr/bin/env python3

import asyncio
import os
from typing import Optional

from fastapi import FastAPI
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig, CallEntity, CreateOutboundCall
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.telephony.server.base import TelephonyServer
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager

app = FastAPI()

# Get environment variables
FREESWITCH_SERVER_URL = os.environ.get("FREESWITCH_SERVER_URL", "http://localhost:8080")
FREESWITCH_API_KEY = os.environ.get("FREESWITCH_API_KEY", "your-api-key")
FREESWITCH_SIP_DOMAIN = os.environ.get("FREESWITCH_SIP_DOMAIN", "")
FREESWITCH_WS_ENDPOINT = os.environ.get("FREESWITCH_WS_ENDPOINT", "ws://localhost:8080/ws")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "your-openai-api-key")
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

# Create a Redis config manager
config_manager = RedisConfigManager(
    redis_host=REDIS_HOST,
    redis_port=REDIS_PORT,
)

# Create a FreeSwitch config
freeswitch_config = FreeSwitchConfig(
    server_url=FREESWITCH_SERVER_URL,
    api_key=FREESWITCH_API_KEY,
    sip_domain=FREESWITCH_SIP_DOMAIN,
    ws_endpoint=FREESWITCH_WS_ENDPOINT,
    input_format="mulaw",
    output_format="mulaw",
    sample_rate=8000,
    channels=1,
)

# Create a telephony server
telephony_server = TelephonyServer(
    base_url=BASE_URL,
    config_manager=config_manager,
)

# Add the telephony server to the FastAPI app
app.include_router(telephony_server.get_router())

# Create a FreeSwitch client
freeswitch_client = FreeSwitchClient(
    base_url=BASE_URL,
    maybe_freeswitch_config=freeswitch_config,
)

@app.post("/make_call")
async def make_call(
    to_phone: str,
    from_phone: Optional[str] = None,
    system_prompt: Optional[str] = None,
):
    """Make an outbound call using FreeSwitch"""
    
    # Set default values
    if not from_phone:
        from_phone = os.environ.get("DEFAULT_FROM_PHONE", "15555555555")
        
    if not system_prompt:
        system_prompt = (
            "You are a helpful AI assistant making a phone call. "
            "Keep your responses brief and conversational. "
            "Introduce yourself at the beginning of the call."
        )
    
    # Create an agent config
    agent_config = ChatGPTAgentConfig(
        initial_message=BaseMessage(text="Hello! I'm an AI assistant calling you through FreeSwitch."),
        prompt_preamble=system_prompt,
        model="gpt-4",
    )
    
    # Create the outbound call request
    outbound_call = CreateOutboundCall(
        recipient=CallEntity(phone_number=to_phone),
        caller=CallEntity(phone_number=from_phone),
        agent_config=agent_config,
        freeswitch_config=freeswitch_config,
    )
    
    # Make the call
    call_id = await freeswitch_client.create_call(
        conversation_id=None,  # Will be generated
        to_phone=to_phone,
        from_phone=from_phone,
        record=True,
    )
    
    return {
        "success": True,
        "call_id": call_id,
        "message": f"Call initiated to {to_phone} from {from_phone}",
    }

@app.get("/active_calls")
async def get_active_calls():
    """Get a list of active calls"""
    active_calls = await freeswitch_client.get_active_calls()
    return {
        "success": True,
        "active_calls": active_calls,
    }

@app.post("/end_call/{call_id}")
async def end_call(call_id: str):
    """End an active call"""
    success = await freeswitch_client.end_call(call_id)
    return {
        "success": success,
        "call_id": call_id,
        "message": f"Call {call_id} {'ended successfully' if success else 'could not be ended'}",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)