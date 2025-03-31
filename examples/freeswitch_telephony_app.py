import asyncio
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vocode.streaming.agent.chat_gpt_agent import ChatGPTAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.telephony.server.base import (
    FreeSwitchInboundCallConfig,
    TelephonyServer,
)

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

# Create a FreeSWITCH config
freeswitch_config = FreeSwitchConfig(
    api_url=os.getenv("FREESWITCH_API_URL", "http://localhost:8080"),
    auth_username=os.getenv("FREESWITCH_AUTH_USERNAME", "freeswitch"),
    auth_password=os.getenv("FREESWITCH_AUTH_PASSWORD", "password"),
    record=True,
)

# Create a ChatGPT agent config
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm an AI assistant. How can I help you today?"),
    prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
Be concise and engaging. Ask questions when appropriate.""",
    model="gpt-3.5-turbo",
)

# Create a FreeSWITCH inbound call config
freeswitch_inbound_call_config = FreeSwitchInboundCallConfig(
    url="/inbound_call",
    agent_config=agent_config,
    freeswitch_config=freeswitch_config,
)

# Create a TelephonyServer
base_url = os.getenv("BASE_URL", "localhost:8000")
telephony_server = TelephonyServer(
    base_url=base_url,
    config_manager=redis_config_manager,
    inbound_call_configs=[freeswitch_inbound_call_config],
)

# Include the telephony server router in the FastAPI app
app.include_router(telephony_server.get_router())


# Create an endpoint to initiate an outbound call
@app.post("/outbound_call")
async def outbound_call(to_phone: str, from_phone: str, agent_id: Optional[str] = None):
    """
    Initiate an outbound call using FreeSWITCH
    """
    # Create a FreeSWITCH client
    freeswitch_client = FreeSwitchClient(
        base_url=base_url,
        maybe_freeswitch_config=freeswitch_config,
    )

    # Create a ChatGPT agent config
    agent_config = ChatGPTAgentConfig(
        initial_message=BaseMessage(text="Hello! I'm an AI assistant calling you. How can I help you today?"),
        prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
Be concise and engaging. Ask questions when appropriate.""",
        model="gpt-3.5-turbo",
    )

    # Create a conversation ID
    from vocode.streaming.utils import create_conversation_id
    conversation_id = create_conversation_id()

    # Create a call config
    from vocode.streaming.models.telephony import FreeSwitchCallConfig
    call_config = FreeSwitchCallConfig(
        transcriber_config=FreeSwitchCallConfig.default_transcriber_config(),
        agent_config=agent_config,
        synthesizer_config=FreeSwitchCallConfig.default_synthesizer_config(),
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
    return await telephony_server.end_outbound_call(conversation_id)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)