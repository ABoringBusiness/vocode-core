# Deploying FreeSWITCH Integration on Hetzner Cloud

This guide explains how to deploy the Vocode FreeSWITCH integration on Hetzner Cloud using GitHub Actions.

## Prerequisites

1. A Hetzner Cloud account
2. A GitHub repository with the Vocode FreeSWITCH integration
3. GitHub Actions enabled for your repository

## Setup

### 1. Create a Hetzner API Token

1. Log in to your Hetzner Cloud Console
2. Go to "Security" > "API Tokens"
3. Click "Generate API Token"
4. Give it a name (e.g., "github-actions")
5. Select "Read & Write" permissions
6. Copy the token (you won't be able to see it again)

### 2. Create an SSH Key

1. Generate an SSH key pair if you don't already have one:
   ```bash
   ssh-keygen -t ed25519 -C "github-actions"
   ```
2. Add the public key to your Hetzner Cloud account:
   - Go to "Security" > "SSH Keys"
   - Click "Add SSH Key"
   - Paste your public key
   - Give it a name (e.g., "github-actions")

### 3. Add GitHub Secrets

Add the following secrets to your GitHub repository:

1. `HETZNER_API_TOKEN`: Your Hetzner API token
2. `SSH_PRIVATE_KEY`: Your SSH private key (the contents of the private key file)
3. `OPENAI_API_KEY`: Your OpenAI API key

## Deployment

### Manual Deployment

1. Go to the "Actions" tab in your GitHub repository
2. Select the "Deploy FreeSWITCH Integration to Hetzner" workflow
3. Click "Run workflow"
4. Select the environment (staging or production)
5. Click "Run workflow"

### Automatic Deployment

You can also configure the workflow to run automatically on specific events, such as pushes to the main branch or releases. Edit the `.github/workflows/deploy-freeswitch.yml` file to add the desired triggers.

## Server Configuration

The deployment workflow will:

1. Create a server if it doesn't exist
2. Install Docker and Docker Compose
3. Copy the Docker Compose files
4. Configure the environment variables
5. Deploy the FreeSWITCH integration

## Accessing the Server

After deployment, you can access the server using SSH:

```bash
ssh root@<server-ip>
```

The FreeSWITCH integration will be available at:

- API endpoint: `http://<server-ip>:8000`
- ESL port: `<server-ip>:8021`

## Troubleshooting

### Checking Logs

You can check the logs of the services:

```bash
ssh root@<server-ip> 'cd /root/vocode-freeswitch && docker compose logs'
```

### Restarting Services

If you need to restart the services:

```bash
ssh root@<server-ip> 'cd /root/vocode-freeswitch && docker compose restart'
```

### Updating the Deployment

To update the deployment:

1. Push your changes to the repository
2. Run the deployment workflow again

## Security Considerations

- The deployment uses a root user for simplicity, but in a production environment, you should use a non-root user with sudo privileges.
- The server exposes ports 8000 (API) and 8021 (ESL) to the public internet. Consider using a firewall to restrict access to these ports.
- The deployment uses HTTP, not HTTPS. In a production environment, you should use HTTPS with a valid SSL certificate.

## Cost Considerations

The deployment uses a cx21 server type, which costs approximately €5.83 per month. You can change the server type in the workflow file to use a different server type.