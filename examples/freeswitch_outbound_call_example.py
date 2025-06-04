import asyncio
import os
from typing import Optional

from dotenv import load_dotenv
from loguru import logger

from vocode.streaming.agent.chat_gpt_agent import ChatGPTAgent
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import CallEntity, CreateOutboundCall, FreeSwitchConfig
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.utils import create_conversation_id

load_dotenv()

# Get FreeSWITCH credentials from environment variables
FREESWITCH_HOST = os.getenv("FREESWITCH_HOST", "localhost")
FREESWITCH_PORT = int(os.getenv("FREESWITCH_PORT", "8021"))
FREESWITCH_PASSWORD = os.getenv("FREESWITCH_PASSWORD", "ClueCon")

# Get OpenAI API key from environment variables
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Create a Redis config manager
config_manager = RedisConfigManager(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
)

# Create a ChatGPT agent config
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm your AI assistant calling you. How can I help you today?"),
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

async def make_outbound_call():
    # Create a FreeSWITCH client
    freeswitch_client = FreeSwitchClient(
        base_url=os.getenv("BASE_URL", "http://localhost:8000"),
        maybe_freeswitch_config=freeswitch_config,
        record_calls=True,
    )
    
    # Create a conversation ID
    conversation_id = create_conversation_id()
    
    # Create an outbound call
    outbound_call = CreateOutboundCall(
        recipient=CallEntity(phone_number=os.getenv("TO_PHONE", "+1234567890")),
        caller=CallEntity(phone_number=os.getenv("FROM_PHONE", "+0987654321")),
        agent_config=agent_config,
        freeswitch_config=freeswitch_config,
        conversation_id=conversation_id,
    )
    
    # Save the call config
    await config_manager.save_config(
        conversation_id,
        outbound_call,
    )
    
    # Make the call
    try:
        call_id = await freeswitch_client.create_call(
            conversation_id=conversation_id,
            to_phone=outbound_call.recipient.phone_number,
            from_phone=outbound_call.caller.phone_number,
            record=True,
        )
        logger.info(f"Created outbound call with ID: {call_id}")
        
        # Wait for the call to complete (you might want to implement a better way to wait)
        await asyncio.sleep(300)  # Wait for 5 minutes
        
        # End the call
        await freeswitch_client.end_call(call_id)
        logger.info(f"Ended call with ID: {call_id}")
    except Exception as e:
        logger.error(f"Error making outbound call: {e}")

if __name__ == "__main__":
    asyncio.run(make_outbound_call())