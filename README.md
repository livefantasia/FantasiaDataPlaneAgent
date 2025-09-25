# DataPlane Agent

A high-performance, type-safe FastAPI service for processing usage data, session lifecycle events, and quota management in a distributed speech processing system.

## 🎯 Overview

The DataPlane Agent is a critical component that bridges AudioAPIServer instances with the ControlPlane, providing:

- **Message Processing**: Consumes and processes usage records, session lifecycle events, and quota refresh requests from Redis queues
- **Data Enrichment**: Enriches raw usage data with server metadata and processing timestamps
- **ControlPlane Integration**: Forwards processed data to the ControlPlane with robust retry mechanisms
- **Health Monitoring**: Provides comprehensive health checks and Prometheus metrics
- **Remote Commands**: Executes remote commands from the ControlPlane for management and monitoring

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  AudioAPIServer │────▶│  Redis Queues   │────▶│ DataPlane Agent │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                                          │
                                                          ▼
                                              ┌─────────────────┐
                                              │  ControlPlane   │
                                              └─────────────────┘
```

### Key Components

- **RedisConsumerService**: Processes messages from Redis queues with dead letter queue support
- **ControlPlaneClient**: HTTP client with JWT authentication and exponential backoff retry
- **CommandProcessor**: Handles remote commands from ControlPlane
- **HealthMetricsService**: Manages server registration, heartbeats, and metrics collection

## 🚀 Features

### ✅ MVP Requirements Implemented

- [x] **Redis Queue Processing**: Reliable message consumption from multiple queues
- [x] **Data Validation**: Strict Pydantic models with runtime validation
- [x] **ControlPlane Communication**: Robust HTTP client with authentication
- [x] **Health Monitoring**: Comprehensive health checks and status reporting
- [x] **Metrics Collection**: Prometheus-compatible metrics and JSON endpoints
- [x] **Command Processing**: Remote command execution from ControlPlane
- [x] **Error Handling**: Dead letter queues and graceful error recovery
- [x] **Type Safety**: Full mypy compliance with strict type checking

### 🔧 Configuration

Environment-based configuration using Pydantic BaseSettings:

### 📝 Logging

The application features comprehensive structured logging in log4j-style format with best practices:

#### Features
- **log4j-style Format**: `timestamp [level]: message {json_context}`
- **Structured Context**: JSON context data for easy parsing and analysis
- **System Context**: Automatic inclusion of process ID (pid) and hostname
- **Correlation IDs**: Request tracing with automatic correlation ID injection
- **Exception Handling**: Full stack traces with contextual error information
- **Service-oriented Logging**: Consistent serviceName and operationName fields

#### Configuration
```bash
# Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL=INFO

# The application uses log4j-style format by default
# Set json_output=True in configure_logging() for pure JSON output
```

#### Usage Examples
```python
from utils import get_logger, log_exception, set_correlation_id

# Service-oriented logging with consistent format
logger = get_logger(__name__)
logger.info("Operation completed: BillingService.getBillingOverview",
           serviceName="BillingService",
           operationName="getBillingOverview", 
           duration=2,
           success=True)

# Error logging with full context
try:
    # Some operation that might fail
    pass
except Exception as e:
    log_exception(logger, e, "Database operation failed: DatabaseService.executeQuery",
                 serviceName="DatabaseService",
                 operationName="executeQuery",
                 queryType="SELECT")

# Set correlation ID for request tracing
correlation_id = set_correlation_id("req-123-abc")
logger.info("Processing user request", serviceName="AuthService", userId="user123")
```

#### Sample Output

log4j-style format:
```
2025-09-25T03:21:53.717866Z [info]: DataPlane Agent started successfully {"correlation_id":"app-startup-001","debug_mode":false,"environment":"production","hostname":"server-001","operationName":"startup","pid":1234,"region":"us-east-1","server_id":"dataplane-agent-001","serviceName":"DataPlaneAgent","version":"1.0.0"}

2025-09-25T03:21:53.718147Z [warning]: Redis connection pool nearing capacity {"correlation_id":"req-456","current_connections":8,"hostname":"server-001","max_connections":10,"operationName":"monitorConnections","pid":1234,"serviceName":"RedisClient","utilization_percent":80.0}
```

Pure JSON format (when json_output=True):
```json
{
  "correlation_id": "req-123-abc",
  "event": "Operation completed: BillingService.getBillingOverview",
  "hostname": "server-001",
  "level": "info",
  "operationName": "getBillingOverview",
  "pid": 1234,
  "serviceName": "BillingService",
  "success": true,
  "timestamp": "2025-09-25T03:21:53.717866Z"
}
```

```python
# Key configuration sections
redis_config: RedisConfig          # Redis connection settings
control_plane_config: ControlPlaneConfig  # ControlPlane API settings
server_config: ServerConfig       # Server identification and region
health_config: HealthConfig       # Health check intervals and endpoints
```

### 📊 Data Models

Comprehensive Pydantic models for:

- **UsageRecord**: Raw usage data from AudioAPIServer
- **EnrichedUsageRecord**: Usage data enriched with server metadata
- **SessionLifecycleEvent**: Session start/complete events
- **RemoteCommand**: Commands from ControlPlane
- **QuotaRefreshRequest**: Quota management requests

## 📦 Installation

### Prerequisites

- Python 3.9+
- Redis Server
- Access to ControlPlane API

### Setup

```bash
# Clone and navigate to the project
cd DataPlaneAgent

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install -r requirements-dev.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your settings
```

### Environment Configuration

```bash
# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password
REDIS_DB=0

# ControlPlane Configuration
CONTROL_PLANE_BASE_URL=https://api.controlplane.com
CONTROL_PLANE_API_KEY=your_api_key
CONTROL_PLANE_TIMEOUT=30

# Server Configuration
SERVER_ID=dataplane-001
SERVER_REGION=us-west-2
SERVER_VERSION=1.0.0
```

## 🏃 Running the Service

### Development

```bash
# Start the service
python main.py

# Or use uvicorn directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# With gunicorn
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app

# With Docker (if Dockerfile exists)
docker build -t dataplane-agent .
docker run -p 8000:8000 --env-file .env dataplane-agent
```

## 🧪 Testing

### Quick Test Run

```bash
# Run all tests with coverage
python run_tests.py

# Or specific test suites
python run_tests.py unit        # Unit tests only
python run_tests.py integration # Integration tests only
python run_tests.py type        # Type checking only
python run_tests.py lint        # Code linting only
```

### Manual Testing

```bash
# Check service health
curl http://localhost:8000/health/

# Get detailed metrics
curl http://localhost:8000/health/detailed

# Prometheus metrics
curl http://localhost:8000/metrics/
```

### Test Coverage

The project includes comprehensive test coverage:

- **Unit Tests**: Test individual components in isolation
- **Integration Tests**: Test component interactions
- **API Tests**: Test HTTP endpoints and responses
- **End-to-End Tests**: Test complete workflows

Current test coverage target: **95%+**

## 📋 API Endpoints

### Health & Monitoring

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health/` | GET | Basic health status |
| `/health/detailed` | GET | Detailed health with metrics |
| `/metrics/` | GET | Prometheus metrics (text) |
| `/metrics/json` | GET | JSON-formatted metrics |

### Documentation

| Endpoint | Description |
|----------|-------------|
| `/docs` | Swagger UI documentation |
| `/redoc` | ReDoc documentation |
| `/openapi.json` | OpenAPI schema |

## 🏗️ Development

### Code Quality Standards

- **Type Safety**: 100% mypy compliance with strict mode
- **Code Style**: Black formatting with line length 88
- **Linting**: flake8 with additional plugins
- **Security**: bandit security scanning
- **Testing**: pytest with async support

### Development Workflow

```bash
# Format code
black dataplane_agent/ tests/

# Type checking
mypy . --strict

# Run linting
flake8 . tests/

# Run tests with coverage
pytest tests/ --cov=. --cov-report=html

# Run all quality checks
python run_tests.py all
```

### Project Structure

```
DataPlaneAgent/
├── __init__.py              # Package initialization
├── main.py                  # FastAPI application entry point
├── config/                  # Configuration management
│   └── __init__.py
├── models/                  # Pydantic data models
│   └── __init__.py
├── services/                # Business logic services
│   ├── redis_client.py      # Redis connectivity
│   ├── control_plane_client.py  # ControlPlane HTTP client
│   ├── redis_consumer.py    # Message queue consumer
│   ├── command_processor.py # Remote command processing
│   └── health_metrics.py    # Health monitoring
├── routers/                 # FastAPI route handlers
│   ├── health.py           # Health check endpoints
│   └── metrics.py          # Metrics endpoints
├── utils/                   # Utility functions
│   ├── __init__.py
│   └── logging.py          # Structured logging
├── tests/                   # Test suite
│   ├── unit/               # Unit tests
│   ├── integration/        # Integration tests
│   └── conftest.py        # Pytest configuration
├── .venv/                  # Virtual environment
├── requirements.txt        # Dependencies
└── README.md              # This file
```

## 🚀 Deployment

### Production Considerations

1. **Environment Variables**: Ensure all required environment variables are set
2. **Redis Connectivity**: Verify Redis server accessibility and authentication
3. **ControlPlane Access**: Confirm API endpoints and authentication keys
4. **Resource Limits**: Configure appropriate CPU and memory limits
5. **Monitoring**: Set up log aggregation and metrics collection
6. **Scaling**: Consider horizontal scaling for high-throughput scenarios

### Health Checks

The service provides multiple health check endpoints for different use cases:

- **Kubernetes Liveness**: `GET /health/` (basic health)
- **Kubernetes Readiness**: `GET /health/detailed` (dependency checks)
- **Load Balancer**: `GET /health/` (lightweight check)

### Metrics & Monitoring

- **Prometheus Metrics**: Available at `/metrics/`
- **Custom Metrics**: Queue depths, processing rates, error counts
- **Health Status**: Component-level health reporting
- **Performance Metrics**: Request latency, throughput statistics

## 🤝 Contributing

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/new-feature`
3. **Make your changes** following the code quality standards
4. **Run tests**: `python run_tests.py all`
5. **Commit your changes**: `git commit -am 'Add new feature'`
6. **Push to the branch**: `git push origin feature/new-feature`
7. **Create a Pull Request**

### Code Review Guidelines

- All code must pass type checking and linting
- Test coverage must remain above 95%
- New features require comprehensive tests
- Breaking changes require documentation updates

## 📝 License

This project is proprietary software. All rights reserved.

## 🆘 Support

For support and questions:

1. Check the [API documentation](http://localhost:8000/docs) when running locally
2. Review the comprehensive test suite for usage examples
3. Check logs for detailed error information
4. Verify configuration and environment variables

## 🔄 Version History

- **v1.0.0**: Initial MVP implementation
  - Redis queue processing
  - ControlPlane integration
  - Health monitoring
  - Comprehensive test suite

---

**Built with ❤️ for high-performance data processing**
