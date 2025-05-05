# FreeSwitch Integration for Vocode

This document provides instructions for setting up and using the FreeSwitch integration with Vocode.

## Overview

The FreeSwitch integration allows you to:
- Make outbound calls using FreeSwitch
- Receive inbound calls from FreeSwitch
- Stream audio between FreeSwitch and Vocode in real-time
- Handle call events (hangup, DTMF, etc.)

## Prerequisites

1. A running FreeSwitch server
2. FreeSwitch configured with the necessary modules:
   - `mod_websocket`
   - `mod_audio_fork`
   - `mod_json_cdr`
   - `mod_commands`

## Installation

### 1. Install FreeSwitch

Follow the official FreeSwitch installation guide for your platform:
https://freeswitch.org/confluence/display/FREESWITCH/Installation

### 2. Install Required Modules

Ensure the following modules are loaded in your FreeSwitch configuration:

```xml
<load module="mod_websocket"/>
<load module="mod_audio_fork"/>
<load module="mod_json_cdr"/>
<load module="mod_commands"/>
```

### 3. Configure Audio Settings

Configure FreeSwitch to use the appropriate audio settings:

```xml
<configuration name="switch.conf" description="Core Configuration">
  <settings>
    <param name="rtp-start-port" value="16384"/>
    <param name="rtp-end-port" value="32768"/>
    <param name="rtp-enable-zrtp" value="true"/>
  </settings>
</configuration>
```

### 4. Configure WebSocket for Audio Streaming

Add a WebSocket configuration to your FreeSwitch setup:

```xml
<configuration name="websocket.conf" description="WebSocket Configuration">
  <settings>
    <param name="listen-ip" value="0.0.0.0"/>
    <param name="listen-port" value="8080"/>
    <param name="debug" value="1"/>
  </settings>
</configuration>
```

## Usage

### Setting Up the Vocode Server

1. Configure your Vocode server with FreeSwitch credentials:

```python
from vocode.streaming.models.telephony import FreeSwitchConfig
from vocode.streaming.telephony.server.base import TelephonyServer, FreeSwitchInboundCallConfig
from vocode.streaming.models.agent import AgentConfig

# Create a FreeSwitch config
freeswitch_config = FreeSwitchConfig(
    server_url="http://your-freeswitch-server:8080",
    api_key="your-api-key",
    sip_domain="your-sip-domain",
    ws_endpoint="ws://your-freeswitch-server:8080/ws",
    input_format="mulaw",  # or "pcm", "opus"
    output_format="mulaw",  # or "pcm", "opus"
    sample_rate=8000,
    channels=1,
)

# Create an inbound call config
inbound_call_config = FreeSwitchInboundCallConfig(
    url="/inbound/freeswitch",
    agent_config=AgentConfig(...),  # Your agent config
    freeswitch_config=freeswitch_config,
)

# Initialize the telephony server
telephony_server = TelephonyServer(
    base_url="your-server-url",
    config_manager=your_config_manager,
    inbound_call_configs=[inbound_call_config],
)
```

### Making Outbound Calls

```python
from vocode.streaming.telephony.client.freeswitch_client import FreeSwitchClient
from vocode.streaming.models.telephony import FreeSwitchConfig

# Create a FreeSwitch client
freeswitch_client = FreeSwitchClient(
    base_url="your-server-url",
    maybe_freeswitch_config=FreeSwitchConfig(
        server_url="http://your-freeswitch-server:8080",
        api_key="your-api-key",
    ),
)

# Make an outbound call
call_id = await freeswitch_client.create_call(
    conversation_id="unique-conversation-id",
    to_phone="destination-number",
    from_phone="source-number",
    record=True,  # Optional: record the call
)
```

### Handling Inbound Calls

1. Configure your FreeSwitch dialplan to forward calls to your Vocode server:

```xml
<extension name="vocode_inbound">
  <condition field="destination_number" expression="^(your-number)$">
    <action application="set" data="hangup_after_bridge=true"/>
    <action application="set" data="continue_on_fail=true"/>
    <action application="set" data="vocode_url=https://your-vocode-server/inbound/freeswitch"/>
    <action application="lua" data="vocode_bridge.lua"/>
  </condition>
</extension>
```

2. Create a `vocode_bridge.lua` script in your FreeSwitch scripts directory:

```lua
-- vocode_bridge.lua
local vocode_url = session:getVariable("vocode_url")
local caller_id = session:getVariable("caller_id_number")
local destination = session:getVariable("destination_number")
local call_uuid = session:getVariable("uuid")

-- Prepare the request to Vocode
local request = {
    call_id = call_uuid,
    from = caller_id,
    to = destination,
    event = "answer"
}

-- Send the request to Vocode
local response = api:execute("curl", vocode_url .. " -X POST -d '" .. json.encode(request) .. "' -H 'Content-Type: application/json'")
local response_data = json.decode(response)

if response_data and response_data.success then
    -- Connect to the WebSocket for audio streaming
    session:execute("audio_fork", response_data.websocket_url)
    
    -- Wait for the call to end
    while session:ready() do
        session:sleep(1000)
    end
else
    session:hangup()
end
```

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**
   - Check that your FreeSwitch server is accessible from your Vocode server
   - Verify that the WebSocket module is properly loaded in FreeSwitch
   - Check firewall settings to ensure WebSocket ports are open

2. **Audio Quality Issues**
   - Ensure the audio format settings match between FreeSwitch and Vocode
   - Check network quality between FreeSwitch and Vocode servers
   - Try different audio formats (mulaw, pcm, opus) to find the best quality

3. **Call Setup Failures**
   - Verify API credentials are correct
   - Check SIP domain configuration
   - Ensure the dialplan is correctly routing calls to Vocode

### Debugging

Enable debug logging in both FreeSwitch and Vocode:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

In FreeSwitch console:

```
console_loglevel debug
```

## Advanced Configuration

### Custom SIP Headers

You can pass custom SIP headers with your calls:

```python
await freeswitch_client.create_call(
    conversation_id="unique-id",
    to_phone="destination",
    from_phone="source",
    telephony_params={
        "sip_headers": {
            "X-Custom-Header": "value",
        }
    }
)
```

### Audio Format Conversion

The FreeSwitch integration supports different audio formats:

- `mulaw`: 8-bit μ-law encoding at 8kHz (default)
- `pcm`: 16-bit linear PCM at 8kHz or 16kHz
- `opus`: Opus codec at 16kHz or 48kHz

Configure the format in your FreeSwitchConfig:

```python
freeswitch_config = FreeSwitchConfig(
    # ... other settings
    input_format="pcm",
    output_format="pcm",
    sample_rate=16000,
    channels=1,
)
```