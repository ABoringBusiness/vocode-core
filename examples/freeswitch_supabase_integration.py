import os
import json
import asyncio
from typing import Optional, Dict, Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

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

# Initialize Supabase client
def get_supabase() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)

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

# Function to get agent config from Supabase
async def get_agent_config(agent_id: str, supabase: Client) -> Optional[ChatGPTAgentConfig]:
    response = supabase.table("agent_configs").select("*").eq("id", agent_id).execute()
    
    if not response.data:
        return None
        
    agent_data = response.data[0]
    
    return ChatGPTAgentConfig(
        initial_message=BaseMessage(text=agent_data.get("initial_message", "Hello! How can I help you today?")),
        prompt_preamble=agent_data.get("prompt_preamble", "You are a helpful AI assistant."),
        model=agent_data.get("model", "gpt-3.5-turbo"),
    )

# Function to log call to Supabase
async def log_call_to_supabase(
    call_data: Dict[str, Any], 
    supabase: Client
) -> None:
    response = supabase.table("call_logs").insert(call_data).execute()
    if hasattr(response, "error") and response.error:
        print(f"Error logging call to Supabase: {response.error}")

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
    
    # Log call completion to Supabase
    try:
        supabase = get_supabase()
        await log_call_to_supabase({
            "conversation_id": conversation_id,
            "to_phone": call_config.to_phone,
            "from_phone": call_config.from_phone,
            "direction": call_config.direction,
            "status": "completed",
            "duration": 0,  # TODO: Calculate actual duration
            "call_uuid": call_config.freeswitch_uuid,
        }, supabase)
    except Exception as e:
        print(f"Error logging call completion: {str(e)}")

# Create an endpoint to initiate an outbound call
@app.post("/outbound_call")
async def outbound_call(
    request: Request,
    supabase: Client = Depends(get_supabase)
):
    # Parse request body
    body = await request.json()
    to_phone = body.get("to_phone")
    from_phone = body.get("from_phone")
    agent_id = body.get("agent_id")
    
    if not to_phone or not from_phone:
        raise HTTPException(status_code=400, detail="Missing required parameters")
    
    # Get agent config from Supabase
    agent_config = None
    if agent_id:
        agent_config = await get_agent_config(agent_id, supabase)
    
    # Use default config if no agent_id or config not found
    if not agent_config:
        agent_config = ChatGPTAgentConfig(
            initial_message=BaseMessage(text="Hello! I'm an AI assistant calling you. How can I help you today?"),
            prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
Be concise and engaging. Ask questions when appropriate.""",
            model="gpt-3.5-turbo",
        )
    
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
    
    # Log call to Supabase
    await log_call_to_supabase({
        "conversation_id": conversation_id,
        "to_phone": to_phone,
        "from_phone": from_phone,
        "direction": "outbound",
        "status": "initiated",
        "agent_id": agent_id,
        "call_uuid": call_uuid,
    }, supabase)

    return {"conversation_id": conversation_id, "call_uuid": call_uuid}

# Create an endpoint to end a call
@app.post("/end_call/{conversation_id}")
async def end_call(
    conversation_id: str,
    supabase: Client = Depends(get_supabase)
):
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
    
    # Log call end to Supabase
    await log_call_to_supabase({
        "conversation_id": conversation_id,
        "status": "ended",
        "call_uuid": call_config.freeswitch_uuid,
    }, supabase)
    
    return {"success": success, "conversation_id": conversation_id}

# Create an endpoint to handle FreeSWITCH events
@app.post("/freeswitch_event")
async def freeswitch_event(
    request: Request,
    supabase: Client = Depends(get_supabase)
):
    """
    Handle FreeSWITCH events
    """
    # Parse request body
    try:
        body = await request.body()
        body_str = body.decode("utf-8")
        
        # Handle both JSON and form data
        if body_str.startswith("{"):
            event_data = json.loads(body_str)
        else:
            event_data = {}
            for item in body_str.split("&"):
                if "=" in item:
                    key, value = item.split("=", 1)
                    event_data[key] = value
    except Exception as e:
        print(f"Error parsing event data: {str(e)}")
        event_data = {}
    
    event_name = event_data.get("Event-Name")
    call_uuid = event_data.get("Unique-ID")
    
    print(f"Received FreeSWITCH event: {event_name} for call {call_uuid}")
    
    # Log event to Supabase
    if call_uuid:
        await log_call_to_supabase({
            "call_uuid": call_uuid,
            "event_name": event_name,
            "event_data": json.dumps(event_data),
        }, supabase)
    
    return {"success": True}

# Create an endpoint to handle inbound calls
@app.post("/inbound_call")
async def inbound_call(
    request: Request,
    supabase: Client = Depends(get_supabase)
):
    """
    Handle inbound calls from FreeSWITCH
    """
    # Parse request body
    body = await request.json()
    to_phone = body.get("to")
    from_phone = body.get("from")
    call_uuid = body.get("uuid")
    agent_id = body.get("agent_id")
    
    if not all([to_phone, from_phone, call_uuid]):
        return {"success": False, "error": "Missing required parameters"}
    
    # Get agent config from Supabase
    agent_config = None
    if agent_id:
        agent_config = await get_agent_config(agent_id, supabase)
    
    # Use default config if no agent_id or config not found
    if not agent_config:
        agent_config = ChatGPTAgentConfig(
            initial_message=BaseMessage(text="Hello! I'm an AI assistant. How can I help you today?"),
            prompt_preamble="""You are a helpful AI assistant on a phone call with a human.
Be concise and engaging. Ask questions when appropriate.""",
            model="gpt-3.5-turbo",
        )
    
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
    
    # Log call to Supabase
    await log_call_to_supabase({
        "conversation_id": conversation_id,
        "to_phone": to_phone,
        "from_phone": from_phone,
        "direction": "inbound",
        "status": "initiated",
        "agent_id": agent_id,
        "call_uuid": call_uuid,
    }, supabase)
    
    # Return the WebSocket URL for FreeSWITCH to connect to
    return {
        "success": True,
        "conversation_id": conversation_id,
        "websocket_url": f"ws://{os.getenv('BASE_URL', 'localhost:8000')}/connect_call/{conversation_id}"
    }

# Create an endpoint to get call history
@app.get("/call_history")
async def call_history(
    limit: int = 100,
    offset: int = 0,
    supabase: Client = Depends(get_supabase)
):
    """
    Get call history from Supabase
    """
    response = supabase.table("call_logs").select("*").order("created_at", desc=True).limit(limit).offset(offset).execute()
    
    return {"calls": response.data}

# Create an endpoint to get agent configs
@app.get("/agent_configs")
async def agent_configs(
    supabase: Client = Depends(get_supabase)
):
    """
    Get agent configs from Supabase
    """
    response = supabase.table("agent_configs").select("*").execute()
    
    return {"agents": response.data}

# Create an endpoint to create/update agent config
@app.post("/agent_configs")
async def create_agent_config(
    request: Request,
    supabase: Client = Depends(get_supabase)
):
    """
    Create or update agent config in Supabase
    """
    body = await request.json()
    
    # Validate required fields
    if not body.get("name") or not body.get("prompt_preamble"):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Check if agent exists
    agent_id = body.get("id")
    if agent_id:
        # Update existing agent
        response = supabase.table("agent_configs").update(body).eq("id", agent_id).execute()
    else:
        # Create new agent
        response = supabase.table("agent_configs").insert(body).execute()
    
    if hasattr(response, "error") and response.error:
        raise HTTPException(status_code=500, detail=str(response.error))
    
    return {"success": True, "agent": response.data[0] if response.data else None}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)