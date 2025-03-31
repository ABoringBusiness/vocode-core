# Vocode FreeSWITCH ESL Integration

This guide explains how to use Vocode with FreeSWITCH Event Socket Library (ESL) for direct, high-performance telephony integration.

## Overview

The FreeSWITCH ESL integration provides several advantages over the HTTP API approach:

1. **Direct Connection**: Establishes a persistent connection to FreeSWITCH for lower latency
2. **Efficient Audio Streaming**: Streams audio directly without HTTP overhead
3. **Real-time Events**: Receives call events in real-time for better call control
4. **Reduced Complexity**: Eliminates the need for an intermediate API server

## Prerequisites

1. A FreeSWITCH server with ESL enabled
2. Python ESL module (`pip install python-ESL`)
3. Redis server for configuration management
4. OpenAI API key for the ChatGPT agent

## Environment Variables

Create a `.env` file with the following variables:

```
# FreeSWITCH Configuration
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

## FreeSWITCH Configuration

### 1. Enable ESL in FreeSWITCH

Ensure your FreeSWITCH server has ESL enabled. In `/etc/freeswitch/autoload_configs/event_socket.conf.xml`:

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

### 2. Configure Dialplan for Inbound Calls

Add a dialplan entry to handle inbound calls in `/etc/freeswitch/dialplan/default/01_vocode.xml`:

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

### 3. Configure Audio Settings

Ensure your FreeSWITCH is configured for the correct audio format:

```xml
<configuration name="switch.conf" description="Core Configuration">
  <settings>
    <param name="rtp-start-port" value="16384"/>
    <param name="rtp-end-port" value="32768"/>
    <param name="rtp-enable-zrtp" value="true"/>
    <param name="sample-rate" value="8000"/>
    <param name="codec-ms" value="20"/>
  </settings>
</configuration>
```

## Running the Application

1. Install the required dependencies:

```bash
pip install -r requirements.txt
pip install python-ESL
```

2. Run the application:

```bash
python freeswitch_esl_app.py
```

## API Endpoints

### Inbound Calls

FreeSWITCH should be configured to send a WebSocket connection to `/inbound_call` when a call is received. The request should include:

```
?to=destination_number&from=caller_number&uuid=call_uuid
```

### Outbound Calls

To initiate an outbound call, send a POST request to `/outbound_call` with the following parameters:

```json
{
  "to_phone": "destination_number",
  "from_phone": "caller_number"
}
```

### End Calls

To end a call, send a POST request to `/end_call/{conversation_id}`.

## Advanced Usage

### Custom Agent Configuration

You can store agent configurations in Supabase or another database and reference them by ID:

```json
{
  "to_phone": "destination_number",
  "from_phone": "caller_number",
  "agent_id": "your-agent-id"
}
```

### Call Events

FreeSWITCH events can be sent to the `/freeswitch_event` endpoint for processing. Configure FreeSWITCH to send events using the `api_hangup_hook` parameter or by subscribing to events in your application.

### Audio Processing

The ESL integration handles audio streaming directly between FreeSWITCH and Vocode. You can customize the audio processing pipeline by modifying the `FreeSwitchESLConversation` class.

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

## Performance Considerations

The ESL integration is designed for high performance, but there are some considerations:

1. **Connection Pooling**: For high call volume, implement connection pooling for ESL
2. **Audio Buffering**: Adjust audio buffer sizes based on your latency requirements
3. **Event Filtering**: Subscribe only to the events you need to reduce overhead
4. **Resource Monitoring**: Monitor memory and CPU usage, especially for concurrent calls