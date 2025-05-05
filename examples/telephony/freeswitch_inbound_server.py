#!/usr/bin/env python3

import os
from typing import Optional

from fastapi import FastAPI
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.server.base import TelephonyServer, FreeSwitchInboundCallConfig
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

# Create an agent config for inbound calls
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! Thank you for calling. How can I assist you today?"),
    prompt_preamble=(
        "You are a helpful AI assistant answering an inbound phone call. "
        "Keep your responses brief and conversational. "
        "Be helpful and friendly."
    ),
    model="gpt-4",
)

# Create an inbound call config
inbound_call_config = FreeSwitchInboundCallConfig(
    url="/inbound/freeswitch",
    agent_config=agent_config,
    freeswitch_config=freeswitch_config,
)

# Create a telephony server
telephony_server = TelephonyServer(
    base_url=BASE_URL,
    config_manager=config_manager,
    inbound_call_configs=[inbound_call_config],
)

# Add the telephony server to the FastAPI app
app.include_router(telephony_server.get_router())

@app.get("/")
async def root():
    return {
        "message": "FreeSwitch Inbound Call Server",
        "status": "running",
        "inbound_endpoint": f"{BASE_URL}/inbound/freeswitch",
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)