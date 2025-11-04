# Chat Gateway Microservice

This project implements a Chat Gateway microservice that abstracts chat connections for multiple platforms such as Twitch and YouTube. It provides a unified interface for managing chat interactions and utilizes a pub/sub layer for efficient message handling.

## Features

- **Unified Chat Interface**: Connect and manage multiple chat platforms seamlessly.
- **Pub/Sub Architecture**: Efficiently handle message flow between platforms using a publish/subscribe model.
- **WebSocket Support**: Real-time communication with clients through WebSocket connections (planned).
- **REST API**: Manage chat platforms and message interactions via a RESTful API (planned).
- **Extensible**: Easily add support for new chat platforms by implementing the defined interfaces.

## Project Structure

```
spoutbreeze-chat-gateway/
├── src/
│   ├── main.py              # Entry point of the microservice
│   └── core/
│       ├── config.py        # Configuration management
│       ├── events.py        # Event handling
│       └── logger.py        # Logging utilities
├── .env                     # Environment variables (not in version control)
├── .env.example            # Example environment configuration
├── Dockerfile              # Container configuration
├── pyproject.toml          # Python project metadata
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Setup Instructions

1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd spoutbreeze-chat-gateway
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the `.env.example` to `.env` and fill in the required values:
   ```bash
   cp .env.example .env
   ```

4. **Run the Microservice**:
   ```bash
   python src/main.py
   ```

## Docker Support

Build and run the microservice using Docker:

```bash
# Build the Docker image
docker build -t chat-gateway .

# Run the container
docker run -p 8000:8000 --env-file .env chat-gateway
```

## Development Status

This project is currently in early development. The following components are implemented:

- ✅ Core configuration management
- ✅ Event handling system
- ✅ Logging utilities
- ✅ Docker support
- 🚧 API routes (planned)
- 🚧 Platform integrations (Twitch, YouTube) (planned)
- 🚧 WebSocket server (planned)
- 🚧 Pub/Sub broker (planned)

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any enhancements or bug fixes.
