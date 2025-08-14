# Testing Guide for DataPlane Agent

This document provides comprehensive information about the test cases and how to run them for the DataPlane Agent project.

## Table of Contents

1. [Test Structure](#test-structure)
2. [Prerequisites](#prerequisites)
3. [Running Tests](#running-tests)
4. [Test Categories](#test-categories)
5. [Test Files Overview](#test-files-overview)
6. [Test Configuration](#test-configuration)
7. [Troubleshooting](#troubleshooting)
8. [Writing New Tests](#writing-new-tests)

## Test Structure

The test suite is organized into two main categories:

```
tests/
├── conftest.py              # Shared test configuration and fixtures
├── unit/                    # Unit tests for individual components
│   ├── test_control_plane_client.py
│   ├── test_models.py
│   └── test_redis_client.py
└── integration/             # Integration tests for component interactions
    ├── test_api_integration.py
    ├── test_end_to_end.py
    └── test_redis_consumer_integration.py
```

## Prerequisites

Before running tests, ensure you have the following installed:

### Required Python Packages

```bash
# Install test dependencies
pip install pytest pytest-asyncio pytest-mock pytest-cov
pip install mypy flake8 black bandit  # For code quality checks
```

### Environment Setup

1. **Virtual Environment**: Ensure you're in the project's virtual environment
2. **Environment Variables**: Set up required environment variables or use a `.env` file:
   ```bash
   SERVER_ID=test-server
   SERVER_REGION=us-east-1
   CONTROL_PLANE_URL=https://api.example.com
   CONTROL_PLANE_API_KEY=test-key
   REDIS_HOST=localhost
   REDIS_PORT=6379
   ```

3. **Redis Server**: For integration tests, ensure Redis is running locally or use Docker:
   ```bash
   docker run -d -p 6379:6379 redis:latest
   ```

## Running Tests

### Using pytest (Recommended)

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage report
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/unit/test_models.py

# Run specific test function
pytest tests/unit/test_models.py::test_usage_record_creation

# Run tests matching a pattern
pytest -k "test_redis"

# Run only unit tests
pytest tests/unit/

# Run only integration tests
pytest tests/integration/
```

### Using the Test Runner Script

```bash
# Run the comprehensive test suite (includes linting, type checking, etc.)
python run_tests.py
```

This script runs:
- Type checking with mypy
- Code linting with flake8
- Code formatting check with black
- Unit tests with pytest
- Integration tests with pytest
- Security analysis with bandit

### Manual Test Execution

```bash
# Type checking
mypy .

# Code linting
flake8 .

# Code formatting
black --check .

# Security analysis
bandit -r . -x tests/
```

## Test Categories

### Unit Tests

Test individual components in isolation:

- **Models Tests** (`test_models.py`): Validate Pydantic models, field validation, serialization
- **Redis Client Tests** (`test_redis_client.py`): Test Redis operations, connection handling
- **Control Plane Client Tests** (`test_control_plane_client.py`): Test API communication, authentication

### Integration Tests

Test component interactions and end-to-end workflows:

- **API Integration** (`test_api_integration.py`): Test FastAPI endpoints and middleware
- **End-to-End** (`test_end_to_end.py`): Test complete workflows from API to data processing
- **Redis Consumer Integration** (`test_redis_consumer_integration.py`): Test message processing pipelines

## Test Files Overview

### `conftest.py`

Contains shared test fixtures and configuration:

```python
# Key fixtures available in all tests:
@pytest.fixture
def mock_config()  # Mocked application configuration

@pytest.fixture
def redis_client()  # Mocked Redis client

@pytest.fixture
def control_plane_client()  # Mocked ControlPlane client
```

### Unit Test Files

#### `test_models.py`

Tests for Pydantic models:
- Model creation and validation
- Field constraints and validators
- Serialization/deserialization
- Error handling for invalid data

**Key Test Cases:**
- `test_usage_record_creation`: Validates UsageRecord model
- `test_session_lifecycle_event`: Tests session event validation
- `test_quota_refresh_models`: Tests quota-related models
- `test_command_models`: Tests remote command models
- `test_server_models`: Tests server registration and metrics

#### `test_redis_client.py`

Tests for Redis operations:
- Connection management
- Queue operations (push/pop)
- Error handling and retries
- Connection pooling

**Key Test Cases:**
- `test_redis_connection`: Tests connection establishment
- `test_queue_operations`: Tests message queuing
- `test_error_handling`: Tests failure scenarios
- `test_connection_retry`: Tests retry mechanisms

#### `test_control_plane_client.py`

Tests for ControlPlane API client:
- HTTP request handling
- Authentication and authorization
- Response parsing
- Error handling and retries

**Key Test Cases:**
- `test_authentication`: Tests API key authentication
- `test_server_registration`: Tests server registration flow
- `test_quota_refresh`: Tests quota refresh requests
- `test_error_responses`: Tests error handling

### Integration Test Files

#### `test_api_integration.py`

Tests for FastAPI application:
- Endpoint functionality
- Request/response handling
- Middleware behavior
- Authentication flows

#### `test_end_to_end.py`

End-to-end workflow tests:
- Complete data processing pipelines
- Service interactions
- Error propagation
- Performance characteristics

#### `test_redis_consumer_integration.py`

Redis message processing tests:
- Message consumption
- Processing workflows
- Error handling and dead letter queues
- Concurrency and performance

## Test Configuration

### Environment Variables for Testing

```bash
# Required for all tests
SERVER_ID=test-server
SERVER_REGION=test-region
CONTROL_PLANE_URL=https://test-api.example.com
CONTROL_PLANE_API_KEY=test-api-key

# Optional test configuration
REDIS_HOST=localhost
REDIS_PORT=6379
LOG_LEVEL=DEBUG
DEBUG=true
```

### pytest Configuration

Create a `pytest.ini` file for custom configuration:

```ini
[tool:pytest]
addopts = -v --tb=short --strict-markers
testpaths = tests
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow running tests
    redis: Tests requiring Redis
```

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   ```bash
   ModuleNotFoundError: No module named 'pytest'
   ```
   **Solution**: Install test dependencies
   ```bash
   pip install pytest pytest-asyncio pytest-mock
   ```

2. **Redis Connection Errors**
   ```bash
   redis.exceptions.ConnectionError: Error connecting to Redis
   ```
   **Solution**: Start Redis server or use Docker
   ```bash
   docker run -d -p 6379:6379 redis:latest
   ```

3. **Environment Variable Errors**
   ```bash
   pydantic_core._pydantic_core.ValidationError: Field required
   ```
   **Solution**: Set required environment variables or create `.env` file

4. **Import Errors**
   ```bash
   ModuleNotFoundError: No module named 'dataplane_agent'
   ```
   **Solution**: Ensure you're in the correct directory and virtual environment

### Debug Mode

Run tests with debug output:

```bash
# Enable debug logging
LOG_LEVEL=DEBUG pytest -v -s

# Run with Python debugger
pytest --pdb

# Run with coverage and HTML report
pytest --cov=. --cov-report=html --cov-report=term
```

## Writing New Tests

### Test Naming Conventions

- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`

### Example Unit Test

```python
import pytest
from models import UsageRecord, ProductCode

def test_usage_record_creation():
    """Test creating a valid UsageRecord."""
    record = UsageRecord(
        transaction_id="test-123",
        user_id="user-456",
        product_code=ProductCode.SPEECH_TO_TEXT,
        usage_amount=100,
        timestamp="2024-01-01T00:00:00Z"
    )
    
    assert record.transaction_id == "test-123"
    assert record.user_id == "user-456"
    assert record.product_code == ProductCode.SPEECH_TO_TEXT
    assert record.usage_amount == 100

def test_usage_record_validation_error():
    """Test UsageRecord validation with invalid data."""
    with pytest.raises(ValueError):
        UsageRecord(
            transaction_id="",  # Invalid empty string
            user_id="user-456",
            product_code=ProductCode.SPEECH_TO_TEXT,
            usage_amount=-10,  # Invalid negative amount
            timestamp="invalid-date"
        )
```

### Example Integration Test

```python
import pytest
from fastapi.testclient import TestClient
from main import app

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoint(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@pytest.mark.asyncio
async def test_async_operation():
    """Test asynchronous operations."""
    # Your async test code here
    pass
```

### Test Markers

Use pytest markers to categorize tests:

```python
@pytest.mark.unit
def test_model_validation():
    pass

@pytest.mark.integration
def test_api_endpoint():
    pass

@pytest.mark.slow
def test_performance():
    pass

@pytest.mark.redis
def test_redis_operations():
    pass
```

Run specific marker groups:

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"
```

## Continuous Integration

For CI/CD pipelines, use:

```bash
# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock pytest-cov

# Run full test suite with coverage
pytest --cov=. --cov-report=xml --cov-report=term

# Generate coverage reports
coverage html
```

## Test Coverage Goals

- **Unit Tests**: Aim for >90% code coverage
- **Integration Tests**: Cover all major workflows
- **Critical Paths**: 100% coverage for security and data handling

## Performance Testing

For performance testing, consider:

```python
import time
import pytest

@pytest.mark.slow
def test_performance():
    start_time = time.time()
    # Your code here
    end_time = time.time()
    
    assert end_time - start_time < 1.0  # Should complete in under 1 second
```

This comprehensive testing guide should help you understand, run, and extend the test suite for the DataPlane Agent project.