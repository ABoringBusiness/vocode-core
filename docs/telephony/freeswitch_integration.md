# FreeSWITCH Integration Guide

This guide explains how to use Vocode with FreeSWITCH for telephony instead of Twilio or Vonage.

## Table of Contents

- [Overview](#overview)
- [Integration Options](#integration-options)
- [Prerequisites](#prerequisites)
- [Basic Setup](#basic-setup)
- [HTTP API Integration](#http-api-integration)
- [ESL Integration](#esl-integration)
- [Docker Compose Setup](#docker-compose-setup)
- [Supabase Integration](#supabase-integration)
- [Advanced Configuration](#advanced-configuration)
- [Troubleshooting](#troubleshooting)
- [Performance Optimization](#performance-optimization)

## Overview

FreeSWITCH is a powerful open-source telephony platform that can be used as an alternative to commercial services like Twilio or Vonage. Vocode's FreeSWITCH integration allows you to:

- Make and receive phone calls using FreeSWITCH
- Process audio in real-time using Vocode's streaming architecture
- Connect calls to AI agents powered by ChatGPT or other LLMs
- Store call data and agent configurations in Supabase or other databases

## Integration Options

Vocode offers two ways to integrate with FreeSWITCH:

1. **HTTP API Integration**: Uses FreeSWITCH's HTTP API for call control and WebSockets for audio streaming. This is simpler to set up but may have higher latency.

2. **ESL Integration**: Uses FreeSWITCH's Event Socket Library (ESL) for direct communication with FreeSWITCH. This provides lower latency and more control but requires additional setup.

## Prerequisites

- A FreeSWITCH server (self-hosted or cloud-based)
- Redis for call state management
- Python 3.8+ with pip
- For ESL integration: FreeSWITCH ESL Python module (`python-ESL`)

## Basic Setup

### 1. Install Vocode with FreeSWITCH support

```bash
pip install "vocode[telephony]"
```

### 2. Set up environment variables

Create a `.env` file with the following variables:

```
# FreeSWITCH Configuration
FREESWITCH_API_URL=http://your-freeswitch-server:8080
FREESWITCH_AUTH_USERNAME=freeswitch
FREESWITCH_AUTH_PASSWORD=your-password

# For ESL integration
FREESWITCH_ESL_HOST=your-freeswitch-server
FREESWITCH_ESL_PORT=8021
FREESWITCH_ESL_PASSWORD=ClueCon

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# OpenAI API Key
OPENAI_API_KEY=your-openai-api-key

# Base URL for your application
BASE_URL=your-public-url
```

### 3. Configure FreeSWITCH

#### Enable ESL in FreeSWITCH

Edit `/etc/freeswitch/autoload_configs/event_socket.conf.xml`:

```xml
<configuration name="event_socket.conf" description="Socket Client">
  <settings>
    <param name="nat-map" value="false"/>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8021"/>
    <param name="password" value="ClueCon"/>
    <param name="apply-inbound-acl" value="any_v4"/>
  </settings>
</configuration>
```

#### Configure Dialplan for Inbound Calls

Create a dialplan entry in `/etc/freeswitch/dialplan/default/01_vocode.xml`:

```xml
<extension name="vocode_ai">
  <condition field="destination_number" expression="^(AI\d+)$">
    <action application="answer"/>
    <action application="set" data="hangup_after_bridge=true"/>
    <action application="set" data="continue_on_fail=true"/>
    <action application="set" data="api_hangup_hook=curl -X POST http://your-vocode-server:8000/freeswitch_event -d 'Event-Name=CHANNEL_HANGUP&Unique-ID=${uuid}'"/>
    <action application="socket" data="ws://your-vocode-server:8000/inbound_call?to=${destination_number}&from=${caller_id_number}&uuid=${uuid}"/>
  </condition>
</extension>
```

## HTTP API Integration

The HTTP API integration uses FreeSWITCH's HTTP API for call control and WebSockets for audio streaming.

### Example Application

```python
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
```

## ESL Integration

The ESL integration uses FreeSWITCH's Event Socket Library (ESL) for direct communication with FreeSWITCH.

### Installing ESL Python Module

```bash
# Install dependencies
apt-get install -y build-essential git

# Clone FreeSWITCH repository
git clone https://github.com/signalwire/freeswitch.git /tmp/freeswitch

# Build and install ESL Python module
cd /tmp/freeswitch/libs/esl
make pymod
cd python
python setup.py install

# Clean up
rm -rf /tmp/freeswitch
```

### Example Application

```python
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
async def outbound_call(to_phone: str, from_phone: str):
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

# Create an endpoint to handle inbound calls
@app.post("/inbound_call")
async def inbound_call(to: str, from_: str, uuid: str):
    """
    Handle inbound calls from FreeSWITCH
    """
    # Create a conversation ID
    conversation_id = create_conversation_id()
    
    # Create a call config
    call_config = FreeSwitchESLCallConfig(
        transcriber_config=FreeSwitchESLCallConfig.default_transcriber_config(),
        agent_config=agent_config,
        synthesizer_config=FreeSwitchESLCallConfig.default_synthesizer_config(),
        freeswitch_config=freeswitch_config,
        freeswitch_uuid=uuid,
        to_phone=to,
        from_phone=from_,
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
```

## Docker Compose Setup

For easy deployment, you can use the provided Docker Compose setup:

```bash
# Clone the repository
git clone https://github.com/vocodedev/vocode-core.git
cd vocode-core/examples/freeswitch_docker

# Copy the example environment file
cp .env.example .env

# Edit the .env file and add your OpenAI API key
# OPENAI_API_KEY=your-openai-api-key

# Start the Docker Compose stack
docker-compose up -d
```

This will start:
- FreeSWITCH server
- Redis for call state management
- Vocode application with FreeSWITCH ESL integration
- (Optional) Supabase PostgreSQL database

## Supabase Integration

You can use Supabase to store agent configurations, call logs, and transcripts.

### Schema Setup

```sql
-- Create agent_configs table
CREATE TABLE agent_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    description TEXT,
    initial_message TEXT NOT NULL DEFAULT 'Hello! I''m an AI assistant. How can I help you today?',
    prompt_preamble TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'gpt-3.5-turbo',
    temperature FLOAT NOT NULL DEFAULT 0.7,
    max_tokens INTEGER,
    voice_id TEXT,
    voice_provider TEXT DEFAULT 'elevenlabs',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create call_logs table
CREATE TABLE call_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT,
    call_uuid TEXT,
    to_phone TEXT,
    from_phone TEXT,
    direction TEXT CHECK (direction IN ('inbound', 'outbound')),
    status TEXT CHECK (status IN ('initiated', 'in_progress', 'completed', 'failed', 'ended')),
    duration INTEGER,
    agent_id UUID REFERENCES agent_configs(id),
    event_name TEXT,
    event_data JSONB,
    transcript JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create transcripts table for detailed conversation history
CREATE TABLE transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    conversation_id TEXT NOT NULL,
    call_uuid TEXT NOT NULL,
    speaker TEXT NOT NULL CHECK (speaker IN ('human', 'ai')),
    text TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Supabase Client Integration

```python
import os
from supabase import create_client, Client

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)

# Function to fetch agent config
async def get_agent_config(agent_id: str):
    response = supabase.table("agent_configs").select("*").eq("id", agent_id).execute()
    return response.data[0] if response.data else None

# Function to log call to Supabase
async def log_call_to_supabase(call_data: dict):
    response = supabase.table("call_logs").insert(call_data).execute()
    return response.data[0] if response.data else None

# Function to log transcript to Supabase
async def log_transcript_to_supabase(transcript_data: dict):
    response = supabase.table("transcripts").insert(transcript_data).execute()
    return response.data[0] if response.data else None
```

## Advanced Configuration

### Custom Agent Configuration

You can customize the agent configuration to change the behavior of the AI assistant:

```python
from vocode.streaming.models.agent import ChatGPTAgentConfig
from vocode.streaming.models.message import BaseMessage

agent_config = ChatGPTAgentConfig(
    initial_message=BaseMessage(text="Hello! I'm a customer service AI assistant. How can I help you today?"),
    prompt_preamble="""You are a customer service AI assistant on a phone call with a customer.
Be friendly, professional, and helpful. Try to resolve their issues efficiently.
If you don't know something, be honest about it and offer to connect them with a human agent if necessary.""",
    model="gpt-4",
    temperature=0.7,
    max_tokens=150,
)
```

### Custom Transcriber Configuration

You can customize the transcriber configuration to change how audio is transcribed:

```python
from vocode.streaming.models.transcriber import DeepgramTranscriberConfig, PunctuationEndpointingConfig

transcriber_config = DeepgramTranscriberConfig(
    sampling_rate=8000,
    audio_encoding="mulaw",
    chunk_size=3200,
    model="phonecall",
    tier="nova",
    language="en-US",
    endpointing_config=PunctuationEndpointingConfig(
        time_threshold=0.5,
    ),
)
```

### Custom Synthesizer Configuration

You can customize the synthesizer configuration to change how text is converted to speech:

```python
from vocode.streaming.models.synthesizer import ElevenLabsSynthesizerConfig

synthesizer_config = ElevenLabsSynthesizerConfig(
    sampling_rate=8000,
    audio_encoding="mulaw",
    voice_id="EXAVITQu4vr4xnSDxMaL",
    optimize_streaming_latency=2,
)
```

## Troubleshooting

### ESL Connection Issues

If you're having trouble connecting to FreeSWITCH ESL:

1. Ensure FreeSWITCH is running and ESL is enabled
2. Check that the ESL port (default 8021) is accessible
3. Verify the ESL password is correct
4. Check firewall settings

### Audio Quality Issues

If you're experiencing audio quality issues:

1. Ensure the sampling rate and audio encoding match between FreeSWITCH and Vocode
2. Check network latency between FreeSWITCH and Vocode
3. Monitor CPU usage on both servers

### Call Control Issues

If calls aren't being properly controlled:

1. Check that the call UUID is being correctly passed between systems
2. Verify that ESL commands are being executed successfully
3. Monitor FreeSWITCH logs for errors

## Performance Optimization

### Connection Pooling

For high call volume, implement connection pooling for ESL:

```python
class ESLConnectionPool:
    def __init__(self, host, port, password, pool_size=10):
        self.host = host
        self.port = port
        self.password = password
        self.pool_size = pool_size
        self.connections = []
        self.lock = asyncio.Lock()
        
    async def get_connection(self):
        async with self.lock:
            if not self.connections:
                # Create a new connection
                conn = ESL.ESLconnection(self.host, self.port, self.password)
                if not conn.connected():
                    raise ConnectionError(f"Failed to connect to FreeSWITCH ESL at {self.host}:{self.port}")
                return conn
                
            # Return an existing connection
            return self.connections.pop()
            
    async def release_connection(self, conn):
        async with self.lock:
            if len(self.connections) < self.pool_size:
                self.connections.append(conn)
            else:
                # Close the connection if the pool is full
                del conn
```

### Audio Buffering

Adjust audio buffer sizes based on your latency requirements:

```python
# For lower latency (more CPU usage)
FREESWITCH_CHUNK_SIZE = 1600  # 10ms at 8kHz with 16bit samples

# For higher latency (less CPU usage)
FREESWITCH_CHUNK_SIZE = 6400  # 40ms at 8kHz with 16bit samples
```

### Event Filtering

Subscribe only to the events you need to reduce overhead:

```python
# Subscribe only to specific events
esl_con.events("plain", "CHANNEL_ANSWER CHANNEL_HANGUP DTMF")
```