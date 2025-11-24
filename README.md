# Encova Submission Bot RPA

Automated web form submission bot for Encova portal with webhook API support.

## Features

- 🔐 Automated login with Okta authentication
- 📝 Form filling automation
- 🌐 Webhook API for Next.js integration
- 🔄 Queue system with 3 concurrent workers
- 🐳 Dockerized for easy deployment
- ☁️ Railway-ready configuration

## Quick Start

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run webhook server:**
   ```bash
   python webhook_server.py
   ```

4. **Test the webhook:**
   ```bash
   python test_webhook.py
   ```

### Docker Deployment

1. **Build the image:**
   ```bash
   docker build -t encova-bot .
   ```

2. **Run the container:**
   ```bash
   docker run -d \
     -p 5000:5000 \
     -e ENCOVA_USERNAME=your_email@example.com \
     -e ENCOVA_PASSWORD=your_password \
     -e BROWSER_HEADLESS=True \
     encova-bot
   ```

### Railway Deployment

1. **Connect your GitHub repository to Railway**

2. **Set environment variables in Railway dashboard:**
   - `ENCOVA_USERNAME` - Your Encova email
   - `ENCOVA_PASSWORD` - Your Encova password
   - `BROWSER_HEADLESS=True` (already set in Dockerfile)
   - `WEBHOOK_PORT=5000` (Railway will auto-assign)

3. **Deploy** - Railway will automatically build and deploy from the Dockerfile

## API Documentation

See [WEBHOOK_API.md](./WEBHOOK_API.md) for complete API documentation.

### Quick Example

```bash
curl -X POST http://localhost:5000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "action": "start_automation",
    "task_id": "test_123",
    "data": {
      "form_data": {
        "firstName": "John",
        "lastName": "Doe",
        "addressLine1": "123 Main St",
        "zipCode": "12345"
      },
      "dropdowns": {
        "state": "GA",
        "addressType": "Business"
      }
    }
  }'
```

## Queue System

The webhook server uses a queue system with 3 worker threads:
- Maximum 3 concurrent browser instances
- Automatic queue management
- Status tracking with queue positions

See [QUEUE_SYSTEM.md](./QUEUE_SYSTEM.md) for details.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ENCOVA_USERNAME` | Encova portal email | Required |
| `ENCOVA_PASSWORD` | Encova portal password | Required |
| `WEBHOOK_HOST` | Server host | `0.0.0.0` |
| `WEBHOOK_PORT` | Server port | `5000` |
| `BROWSER_HEADLESS` | Run browser in headless mode | `True` |
| `BROWSER_TIMEOUT` | Browser timeout (ms) | `30000` |

## Health Check

```bash
curl http://localhost:5000/health
```

## Queue Status

```bash
curl http://localhost:5000/queue/status
```

## License

MIT
