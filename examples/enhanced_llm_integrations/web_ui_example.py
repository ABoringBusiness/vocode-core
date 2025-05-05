#!/usr/bin/env python3

import os
import asyncio
import uvicorn
from typing import Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from vocode.streaming.models.agent import (
    EnhancedOpenAIAgentConfig,
    EnhancedGroqAgentConfig,
    EnhancedClaudeAgentConfig,
)
from vocode.streaming.models.message import BaseMessage
from vocode.streaming.models.synthesizer import AzureSynthesizerConfig
from vocode.streaming.models.transcriber import DeepgramTranscriberConfig
from vocode.streaming.synthesizer.azure_synthesizer import AzureSynthesizer
from vocode.streaming.transcriber.deepgram_transcriber import DeepgramTranscriber
from vocode.streaming.streaming_conversation import StreamingConversation

# Create FastAPI app
app = FastAPI()

# Get environment variables
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AZURE_SPEECH_KEY = os.environ.get("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.environ.get("AZURE_SPEECH_REGION")
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY")

# Set up templates
templates = Jinja2Templates(directory="templates")

# Create directory for templates if it doesn't exist
os.makedirs("templates", exist_ok=True)

# Create HTML template
with open("templates/index.html", "w") as f:
    f.write("""
<!DOCTYPE html>
<html>
<head>
    <title>Enhanced LLM Integrations</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        select, input, textarea {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            box-sizing: border-box;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 10px 15px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
        }
        button:hover {
            background-color: #45a049;
        }
        .conversation {
            margin-top: 20px;
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            height: 300px;
            overflow-y: auto;
        }
        .user-message {
            background-color: #e6f7ff;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .bot-message {
            background-color: #f0f0f0;
            padding: 8px;
            border-radius: 4px;
            margin-bottom: 10px;
        }
        .status {
            color: #666;
            font-style: italic;
            margin-top: 10px;
        }
        .advanced-options {
            margin-top: 15px;
            border: 1px solid #ddd;
            padding: 10px;
            border-radius: 4px;
        }
        .advanced-toggle {
            cursor: pointer;
            color: #0066cc;
            margin-bottom: 10px;
        }
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <h1>Enhanced LLM Integrations Demo</h1>
    
    <div class="form-group">
        <label for="llm-provider">LLM Provider:</label>
        <select id="llm-provider" name="llm-provider">
            <option value="openai">OpenAI</option>
            <option value="groq">Groq</option>
            <option value="claude">Claude</option>
        </select>
    </div>
    
    <div class="form-group">
        <label for="model-name">Model:</label>
        <select id="model-name" name="model-name">
            <!-- OpenAI models -->
            <option value="gpt-4o" class="openai-model">GPT-4o</option>
            <option value="gpt-4" class="openai-model">GPT-4</option>
            <option value="gpt-3.5-turbo-1106" class="openai-model">GPT-3.5 Turbo</option>
            
            <!-- Groq models -->
            <option value="llama3-70b-8192" class="groq-model hidden">Llama 3 70B</option>
            <option value="llama3-8b-8192" class="groq-model hidden">Llama 3 8B</option>
            <option value="mixtral-8x7b-32768" class="groq-model hidden">Mixtral 8x7B</option>
            
            <!-- Claude models -->
            <option value="claude-3-opus-20240229" class="claude-model hidden">Claude 3 Opus</option>
            <option value="claude-3-sonnet-20240229" class="claude-model hidden">Claude 3 Sonnet</option>
            <option value="claude-3-haiku-20240307" class="claude-model hidden">Claude 3 Haiku</option>
        </select>
    </div>
    
    <div class="form-group">
        <label for="temperature">Temperature:</label>
        <input type="range" id="temperature" name="temperature" min="0" max="1" step="0.1" value="0.7">
        <span id="temperature-value">0.7</span>
    </div>
    
    <div class="advanced-toggle" onclick="toggleAdvanced()">+ Advanced Options</div>
    
    <div id="advanced-options" class="advanced-options hidden">
        <div class="form-group">
            <label for="max-tokens">Max Tokens:</label>
            <input type="number" id="max-tokens" name="max-tokens" value="1024" min="1" max="4096">
        </div>
        
        <div class="form-group">
            <label for="top-p">Top P:</label>
            <input type="range" id="top-p" name="top-p" min="0" max="1" step="0.1" value="0.9">
            <span id="top-p-value">0.9</span>
        </div>
        
        <div class="form-group">
            <label for="frequency-penalty">Frequency Penalty:</label>
            <input type="range" id="frequency-penalty" name="frequency-penalty" min="-2" max="2" step="0.1" value="0">
            <span id="frequency-penalty-value">0</span>
        </div>
        
        <div class="form-group">
            <label for="presence-penalty">Presence Penalty:</label>
            <input type="range" id="presence-penalty" name="presence-penalty" min="-2" max="2" step="0.1" value="0">
            <span id="presence-penalty-value">0</span>
        </div>
        
        <div class="form-group">
            <label for="use-backchannels">Use Backchannels:</label>
            <input type="checkbox" id="use-backchannels" name="use-backchannels" checked>
        </div>
    </div>
    
    <div class="form-group">
        <label for="prompt">System Prompt:</label>
        <textarea id="prompt" name="prompt" rows="3">You are a helpful AI assistant. Be concise, friendly, and helpful in your responses. If you don't know something, admit it rather than making up information.</textarea>
    </div>
    
    <button id="start-button" onclick="startConversation()">Start Conversation</button>
    <button id="stop-button" onclick="stopConversation()" disabled>Stop Conversation</button>
    
    <div class="conversation" id="conversation">
        <div class="status">Start a conversation to begin...</div>
    </div>
    
    <div class="form-group">
        <label for="user-input">Your Message:</label>
        <input type="text" id="user-input" name="user-input" disabled>
    </div>
    
    <button id="send-button" onclick="sendMessage()" disabled>Send</button>
    
    <script>
        let socket;
        let conversationId;
        
        // Update displayed values for sliders
        document.getElementById('temperature').addEventListener('input', function() {
            document.getElementById('temperature-value').textContent = this.value;
        });
        
        document.getElementById('top-p').addEventListener('input', function() {
            document.getElementById('top-p-value').textContent = this.value;
        });
        
        document.getElementById('frequency-penalty').addEventListener('input', function() {
            document.getElementById('frequency-penalty-value').textContent = this.value;
        });
        
        document.getElementById('presence-penalty').addEventListener('input', function() {
            document.getElementById('presence-penalty-value').textContent = this.value;
        });
        
        // Toggle advanced options
        function toggleAdvanced() {
            const advancedOptions = document.getElementById('advanced-options');
            advancedOptions.classList.toggle('hidden');
            
            const toggle = document.querySelector('.advanced-toggle');
            if (advancedOptions.classList.contains('hidden')) {
                toggle.textContent = '+ Advanced Options';
            } else {
                toggle.textContent = '- Advanced Options';
            }
        }
        
        // Update model options based on selected provider
        document.getElementById('llm-provider').addEventListener('change', function() {
            const provider = this.value;
            const modelSelect = document.getElementById('model-name');
            
            // Hide all model options
            document.querySelectorAll('#model-name option').forEach(option => {
                option.classList.add('hidden');
            });
            
            // Show only relevant models
            document.querySelectorAll(`.${provider}-model`).forEach(option => {
                option.classList.remove('hidden');
            });
            
            // Select first visible option
            const firstVisibleOption = document.querySelector(`#model-name option.${provider}-model`);
            if (firstVisibleOption) {
                firstVisibleOption.selected = true;
            }
        });
        
        // Start conversation
        async function startConversation() {
            const provider = document.getElementById('llm-provider').value;
            const model = document.getElementById('model-name').value;
            const temperature = document.getElementById('temperature').value;
            const maxTokens = document.getElementById('max-tokens').value;
            const topP = document.getElementById('top-p').value;
            const frequencyPenalty = document.getElementById('frequency-penalty').value;
            const presencePenalty = document.getElementById('presence-penalty').value;
            const useBackchannels = document.getElementById('use-backchannels').checked;
            const prompt = document.getElementById('prompt').value;
            
            // Create conversation
            const response = await fetch('/create_conversation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    provider,
                    model,
                    temperature: parseFloat(temperature),
                    max_tokens: parseInt(maxTokens),
                    top_p: parseFloat(topP),
                    frequency_penalty: parseFloat(frequencyPenalty),
                    presence_penalty: parseFloat(presencePenalty),
                    use_backchannels: useBackchannels,
                    prompt,
                }),
            });
            
            const data = await response.json();
            conversationId = data.conversation_id;
            
            // Connect to WebSocket
            socket = new WebSocket(`ws://${window.location.host}/ws/${conversationId}`);
            
            socket.onopen = function(e) {
                console.log('WebSocket connection established');
                document.getElementById('conversation').innerHTML = '';
                document.getElementById('start-button').disabled = true;
                document.getElementById('stop-button').disabled = false;
                document.getElementById('user-input').disabled = false;
                document.getElementById('send-button').disabled = false;
                
                // Add initial bot message
                const initialMessage = document.createElement('div');
                initialMessage.className = 'bot-message';
                initialMessage.textContent = data.initial_message;
                document.getElementById('conversation').appendChild(initialMessage);
            };
            
            socket.onmessage = function(event) {
                const message = JSON.parse(event.data);
                
                if (message.type === 'bot') {
                    const botMessage = document.createElement('div');
                    botMessage.className = 'bot-message';
                    botMessage.textContent = message.text;
                    document.getElementById('conversation').appendChild(botMessage);
                    
                    // Scroll to bottom
                    const conversation = document.getElementById('conversation');
                    conversation.scrollTop = conversation.scrollHeight;
                }
            };
            
            socket.onclose = function(event) {
                console.log('WebSocket connection closed');
            };
        }
        
        // Stop conversation
        async function stopConversation() {
            if (socket) {
                socket.close();
            }
            
            if (conversationId) {
                await fetch(`/end_conversation/${conversationId}`, {
                    method: 'POST',
                });
            }
            
            document.getElementById('start-button').disabled = false;
            document.getElementById('stop-button').disabled = true;
            document.getElementById('user-input').disabled = true;
            document.getElementById('send-button').disabled = true;
            
            // Add status message
            const status = document.createElement('div');
            status.className = 'status';
            status.textContent = 'Conversation ended.';
            document.getElementById('conversation').appendChild(status);
        }
        
        // Send message
        function sendMessage() {
            const userInput = document.getElementById('user-input');
            const message = userInput.value.trim();
            
            if (message && socket && socket.readyState === WebSocket.OPEN) {
                // Add user message to conversation
                const userMessage = document.createElement('div');
                userMessage.className = 'user-message';
                userMessage.textContent = message;
                document.getElementById('conversation').appendChild(userMessage);
                
                // Send message to server
                socket.send(JSON.stringify({
                    type: 'user',
                    text: message,
                }));
                
                // Clear input
                userInput.value = '';
                
                // Scroll to bottom
                const conversation = document.getElementById('conversation');
                conversation.scrollTop = conversation.scrollHeight;
            }
        }
        
        // Send message on Enter key
        document.getElementById('user-input').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
    </script>
</body>
</html>
    """)

# Store active conversations
active_conversations = {}

class ConversationConfig(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    use_backchannels: bool
    prompt: str

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/create_conversation")
async def create_conversation(config: ConversationConfig):
    # Generate a unique conversation ID
    conversation_id = f"conv_{len(active_conversations) + 1}"
    
    # Create agent config based on provider
    if config.provider == "openai":
        agent_config = EnhancedOpenAIAgentConfig(
            initial_message=BaseMessage(text="Hello! I'm an AI assistant powered by OpenAI. How can I help you today?"),
            prompt_preamble=config.prompt,
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            openai_api_key=OPENAI_API_KEY,
            top_p=config.top_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
            use_backchannels=config.use_backchannels,
            backchannel_probability=0.6,
        )
    elif config.provider == "groq":
        agent_config = EnhancedGroqAgentConfig(
            initial_message=BaseMessage(text="Hello! I'm an AI assistant powered by Groq. How can I help you today?"),
            prompt_preamble=config.prompt,
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            groq_api_key=GROQ_API_KEY,
            top_p=config.top_p,
            frequency_penalty=config.frequency_penalty,
            presence_penalty=config.presence_penalty,
            use_backchannels=config.use_backchannels,
            backchannel_probability=0.6,
        )
    elif config.provider == "claude":
        agent_config = EnhancedClaudeAgentConfig(
            initial_message=BaseMessage(text="Hello! I'm an AI assistant powered by Claude. How can I help you today?"),
            prompt_preamble=config.prompt,
            model_name=config.model,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            anthropic_api_key=ANTHROPIC_API_KEY,
            top_p=config.top_p,
            use_backchannels=config.use_backchannels,
            backchannel_probability=0.6,
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid provider")
    
    # Create conversation components
    agent = agent_config.create_agent()
    
    # Store agent in active conversations
    active_conversations[conversation_id] = {
        "agent": agent,
        "messages": [],
    }
    
    return {
        "conversation_id": conversation_id,
        "initial_message": agent_config.initial_message.text,
    }

@app.post("/end_conversation/{conversation_id}")
async def end_conversation(conversation_id: str):
    if conversation_id in active_conversations:
        # Clean up resources
        del active_conversations[conversation_id]
        return {"status": "success"}
    else:
        raise HTTPException(status_code=404, detail="Conversation not found")

@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    
    if conversation_id not in active_conversations:
        await websocket.close(code=1000, reason="Conversation not found")
        return
    
    conversation = active_conversations[conversation_id]
    agent = conversation["agent"]
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            if data["type"] == "user":
                user_message = data["text"]
                conversation["messages"].append({"role": "user", "content": user_message})
                
                # Generate response from agent
                response = await agent.respond(
                    human_input=user_message,
                    conversation_id=conversation_id,
                    is_interrupt=False,
                )
                
                # Send response to client
                await websocket.send_json({
                    "type": "bot",
                    "text": response.message.text,
                })
                
                conversation["messages"].append({"role": "assistant", "content": response.message.text})
    
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for conversation {conversation_id}")
    except Exception as e:
        print(f"Error in WebSocket: {e}")
        await websocket.close(code=1000, reason=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)