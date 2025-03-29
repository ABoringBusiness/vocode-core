# Vocode FreeSWITCH Integration

This guide explains how to use Vocode with FreeSWITCH for telephony instead of Twilio or Vonage.

## Prerequisites

1. A FreeSWITCH server set up and running
2. Redis server for configuration management
3. OpenAI API key for the ChatGPT agent

## Environment Variables

Create a `.env` file with the following variables:

```
# FreeSWITCH Configuration
FREESWITCH_API_URL=http://your-freeswitch-server:8080
FREESWITCH_AUTH_USERNAME=freeswitch
FREESWITCH_AUTH_PASSWORD=your-password

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379

# OpenAI API Key
OPENAI_API_KEY=your-openai-api-key

# Base URL for your application
BASE_URL=your-public-url
```

## Running the Application

1. Install the required dependencies:

```bash
pip install -r requirements.txt
```

2. Run the application:

```bash
python freeswitch_telephony_app.py
```

## API Endpoints

### Inbound Calls

FreeSWITCH should be configured to send an HTTP POST request to `/inbound_call` when a call is received. The request body should include:

```json
{
  "to": "destination_number",
  "from": "caller_number",
  "uuid": "call_uuid"
}
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

## FreeSWITCH Configuration

You need to configure FreeSWITCH to work with this application. Here's a basic configuration:

1. Configure FreeSWITCH to send HTTP requests to your application when calls are received.
2. Set up a WebSocket connection for audio streaming.

Refer to the [FreeSWITCH documentation](https://freeswitch.org/confluence/display/FREESWITCH/FreeSWITCH+Documentation) for more details.

## Integration with phoneai_freeswitch

This implementation is designed to work with the [phoneai_freeswitch](https://github.com/ABoringBusiness/phoneai_freeswitch) project. Make sure your FreeSWITCH server is properly configured to communicate with this application.

## Troubleshooting

- Ensure your FreeSWITCH server is accessible from the application.
- Check that the WebSocket connection is properly established.
- Verify that the Redis server is running and accessible.
- Make sure your OpenAI API key is valid.