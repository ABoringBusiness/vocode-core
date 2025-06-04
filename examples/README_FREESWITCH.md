# FreeSWITCH Integration for Vocode

This integration allows Vocode to work with FreeSWITCH for telephony, enabling you to use Vocode's transcription, LLM, and text-to-speech capabilities with FreeSWITCH's powerful telephony features.

## Prerequisites

1. A running FreeSWITCH server with ESL (Event Socket Library) enabled
2. Python 3.10 or higher
3. Redis server (for config management)
4. OpenAI API key (or other LLM provider supported by Vocode)

## Installation

Install Vocode with FreeSWITCH support:

```bash
pip install "vocode[telephony,freeswitchESL]"
```

## Configuration

Set the following environment variables or use a `.env` file:

```
FREESWITCH_HOST=your-freeswitch-server
FREESWITCH_PORT=8021
FREESWITCH_PASSWORD=ClueCon
OPENAI_API_KEY=your-openai-api-key
BASE_URL=your-public-url
REDIS_URL=redis://localhost:6379
```

## Handling Inbound Calls

To handle inbound calls from FreeSWITCH, use the `freeswitch_telephony_example.py` script:

```python
import os
from fastapi import FastAPI
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.telephony.server.base import (
    FreeSwitchInboundCallConfig,
    TelephonyServer,
)

# Create a FastAPI app
app = FastAPI()

# Create a Redis config manager
config_manager = RedisConfigManager(
    redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
)

# Create a ChatGPT agent config
agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm your AI assistant. How can I help you today?"),
    prompt_preamble="You are a helpful AI assistant on a phone call with a human.",
    model="gpt-4o",
    temperature=0.7,
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Create a FreeSWITCH config
freeswitch_config = FreeSwitchConfig(
    host=os.getenv("FREESWITCH_HOST", "localhost"),
    port=int(os.getenv("FREESWITCH_PORT", "8021")),
    password=os.getenv("FREESWITCH_PASSWORD", "ClueCon"),
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
```

## Making Outbound Calls

To make outbound calls using FreeSWITCH, use the `freeswitch_outbound_call_example.py` script:

```python
import asyncio
import os
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.telephony import CallEntity, CreateOutboundCall, FreeSwitchConfig
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.telephony.config_manager.redis_config_manager import RedisConfigManager
from vocode.streaming.utils import create_conversation_id

async def make_outbound_call():
    # Create a Redis config manager
    config_manager = RedisConfigManager(
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379")
    )
    
    # Create a ChatGPT agent config
    agent_config = ChatGPTAgentConfig(
        initial_message=BaseMessage(text="Hello! I'm your AI assistant calling you."),
        prompt_preamble="You are a helpful AI assistant on a phone call with a human.",
        model="gpt-4o",
        temperature=0.7,
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    
    # Create a FreeSWITCH config
    freeswitch_config = FreeSwitchConfig(
        host=os.getenv("FREESWITCH_HOST", "localhost"),
        port=int(os.getenv("FREESWITCH_PORT", "8021")),
        password=os.getenv("FREESWITCH_PASSWORD", "ClueCon"),
        record=True,
    )
    
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
    call_id = await freeswitch_client.create_call(
        conversation_id=conversation_id,
        to_phone=outbound_call.recipient.phone_number,
        from_phone=outbound_call.caller.phone_number,
        record=True,
    )
    
    # Wait for the call to complete
    await asyncio.sleep(300)  # Wait for 5 minutes
    
    # End the call
    await freeswitch_client.end_call(call_id)

if __name__ == "__main__":
    asyncio.run(make_outbound_call())
```

## FreeSWITCH Configuration

To configure FreeSWITCH to work with Vocode, you need to:

1. Enable the Event Socket Library (ESL) in FreeSWITCH
2. Configure a dialplan to route calls to Vocode

### Enable ESL

In your FreeSWITCH configuration, make sure the Event Socket Library is enabled. Edit `/etc/freeswitch/autoload_configs/event_socket.conf.xml`:

```xml
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="ClueCon"/>
  </settings>
</configuration>
```

### Configure Dialplan

Create a dialplan to route calls to Vocode. Edit `/etc/freeswitch/dialplan/default/vocode.xml`:

```xml
<extension name="vocode">
  <condition field="destination_number" expression="^(vocode)$">
    <action application="answer"/>
    <action application="socket" data="your-vocode-server:8000/inbound_call"/>
  </condition>
</extension>
```

Replace `your-vocode-server:8000` with the URL of your Vocode server.

## Advanced Configuration

### Custom Audio Processing

You can customize the audio processing by modifying the FreeSWITCH client and conversation classes. For example, you can:

- Change the audio format (e.g., use LINEAR16 instead of MULAW)
- Adjust the sampling rate
- Implement custom audio processing before sending to Vocode

### Integration with Other FreeSWITCH Features

FreeSWITCH offers many features that can be integrated with Vocode:

- Call recording
- Call transfer
- Conference calls
- IVR menus
- Call queuing

Refer to the FreeSWITCH documentation for more information on these features.

## Troubleshooting

### Connection Issues

If you're having trouble connecting to FreeSWITCH:

1. Check that FreeSWITCH is running and ESL is enabled
2. Verify the host, port, and password are correct
3. Check network connectivity and firewall settings

### Audio Issues

If you're experiencing audio issues:

1. Check the audio format and sampling rate
2. Verify that the audio is being properly encoded/decoded
3. Check for network latency or packet loss

### Logging

Enable debug logging to troubleshoot issues:

```python
import logging
from loguru import logger

logger.add("vocode_freeswitch.log", level="DEBUG")
```

## Support

For more information and support:

- Vocode Documentation: https://docs.vocode.dev/
- FreeSWITCH Documentation: https://freeswitch.org/confluence/
- GitHub Issues: https://github.com/vocodedev/vocode-python/issues