import asyncio
import os
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from loguru import logger

from vocode.streaming.agent.chat_gpt_agent import ChatGPTAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.telephony.server.base import (
    FreeSwitchInboundCallConfig,
    TelephonyServer,
)

load_dotenv()

# Get FreeSWITCH credentials from environment variables
FREESWITCH_HOST = os.getenv("FREESWITCH_HOST", "localhost")
FREESWITCH_PORT = int(os.getenv("FREESWITCH_PORT", "8021"))
FREESWITCH_PASSWORD = os.getenv("FREESWITCH_PASSWORD", "ClueCon")

# Get OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Create a FastAPI app
app = FastAPI()

# Create a Redis config manager
config_manager = RedisConfigManager(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
)

# Create a ChatGPT agent config
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm your AI assistant. How can I help you today?"),
    prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
    Be concise and engaging. Ask questions when appropriate.""",
    model="gpt-4o",
    temperature=0.7,
    api_key=OPENAI_API_KEY,
)

# Create a FreeSWITCH config
freeswitch_config = FreeSwitchConfig(
    host=FREESWITCH_HOST,
    port=FREESWITCH_PORT,
    password=FREESWITCH_PASSWORD,
    record=True,  # Record calls
)

# Create a TelephonyServer
telephony_server = TelephonyServer(
    base_url=os.getenv("BASE_URL", "http://localhost:8000"),
    config_manager=config_manager,
    inbound_call_configs=[
        FreeSwitchInboundCallConfig(
            url="/inbound_call",
            agent_config=agent_config,
            freeswitch_config=freeswitch_config,
        )
    ],
)

# Include the telephony server router in the FastAPI app
app.include_router(telephony_server.get_router())

# Add a health check endpoint
@app.get("/health")
async def health():
    return {"status": "ok"}

# Run the FastAPI app
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)