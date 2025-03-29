# Vocode FreeSWITCH Docker Setup

This directory contains a complete Docker Compose setup for running Vocode with FreeSWITCH integration.

## Components

- **FreeSWITCH**: Open-source telephony platform
- **Redis**: For call state management
- **Vocode App**: FastAPI application with FreeSWITCH ESL integration
- **Supabase DB** (optional): For agent configuration and call history

## Getting Started

1. Copy the example environment file:

```bash
cp .env.example .env
```

2. Edit the `.env` file and add your OpenAI API key:

```
OPENAI_API_KEY=your-openai-api-key
```

3. Start the Docker Compose stack:

```bash
docker-compose up -d
```

4. Check that all services are running:

```bash
docker-compose ps
```

## Making Test Calls

### Using FreeSWITCH CLI

You can connect to the FreeSWITCH CLI to make test calls:

```bash
docker exec -it vocode-freeswitch fs_cli
```

Once in the CLI, you can make a test call:

```
originate sofia/internal/1000@127.0.0.1 &socket('ws://vocode-app:8000/inbound_call?to=1000&from=2000&uuid=${uuid}')
```

### Using the API

You can also make outbound calls using the Vocode API:

```bash
curl -X POST http://localhost:8000/outbound_call \
  -H "Content-Type: application/json" \
  -d '{"to_phone":"1000", "from_phone":"2000"}'
```

## Configuration

### FreeSWITCH Configuration

The FreeSWITCH configuration is mounted from the `freeswitch/conf` directory. You can modify these files to customize your FreeSWITCH setup.

### Vocode Configuration

The Vocode application is configured through environment variables in the `.env` file. You can modify these variables to customize your Vocode setup.

## Troubleshooting

### Checking Logs

You can check the logs of each service:

```bash
# FreeSWITCH logs
docker-compose logs freeswitch

# Vocode app logs
docker-compose logs vocode-app

# Redis logs
docker-compose logs redis
```

### Common Issues

1. **FreeSWITCH ESL Connection Issues**: Make sure the ESL port (8021) is accessible and the password is correct.
2. **Redis Connection Issues**: Make sure Redis is running and accessible.
3. **Audio Quality Issues**: Check the FreeSWITCH audio settings and make sure the codecs are compatible.

## Advanced Usage

### Custom Agent Configuration

You can modify the agent configuration in `app.py` to customize the AI assistant's behavior.

### Supabase Integration

If you want to use Supabase for agent configuration and call history, you can uncomment the Supabase section in `docker-compose.yml` and set up the Supabase client in `app.py`.