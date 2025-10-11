#!/bin/bash

# FantasiaDataPlaneAgent Startup Script with Environment Parameter
set -e

# Default environment
ENVIRONMENT=${1:-development}

# Validate environment parameter
if [[ ! "$ENVIRONMENT" =~ ^(development|test|production)$ ]]; then
    echo "❌ Invalid environment: $ENVIRONMENT"
    echo "Usage: $0 [development|test|production]"
    exit 1
fi

echo "🚀 Starting FantasiaDataPlaneAgent in $ENVIRONMENT mode..."

# Check if environment file exists
ENV_FILE=".env.$ENVIRONMENT"
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ $ENV_FILE file not found!"
    echo "Please copy .env.example to $ENV_FILE and configure your settings."
    exit 1
fi

# Load environment variables
export NODE_ENV=$ENVIRONMENT
source "$ENV_FILE"

echo "🔧 Checking uv installation..."
if ! command -v uv &> /dev/null; then
    echo "❌ uv is required but not installed."
    echo "Please install uv: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "🐍 Setting up Python environment with uv..."
if [ ! -f "pyproject.toml" ]; then
    echo "❌ No pyproject.toml found."
    exit 1
fi

# Create virtual environment and install dependencies
echo "📦 Installing dependencies from pyproject.toml..."
if [ "$ENVIRONMENT" = "production" ]; then
    uv sync --no-dev
else
    uv sync
fi

# Environment-specific checks and actions
case $ENVIRONMENT in
    "development")
        echo "🔍 Running type check..."
        if command -v mypy &> /dev/null && [ -f "mypy.ini" ]; then
            uv run mypy .
        fi
        
        echo "🧹 Running linter..."
        if command -v ruff &> /dev/null; then
            uv run ruff check .
        elif command -v flake8 &> /dev/null; then
            uv run flake8 .
        fi
        
        echo "🔍 Checking Redis connection..."
        if ! uv run python -c "import redis; r = redis.Redis(host='$REDIS_HOST', port=$REDIS_PORT, password='$REDIS_PASSWORD', db=$REDIS_DB); r.ping(); print('Redis connection successful')" 2>/dev/null; then
            echo "⚠️  Redis connection failed. Please ensure Redis is running and configured correctly."
        fi
        
        echo "🌐 Checking Control Plane connectivity..."
        if ! curl -f -s "$CONTROL_PLANE_URL/health" > /dev/null 2>&1; then
            echo "⚠️  Control Plane not reachable at $CONTROL_PLANE_URL. Agent will retry on startup."
        fi
        ;;
        
    "test")
        echo "🧪 Running tests..."
        if [ -f "pytest.ini" ] || [ -d "tests/" ]; then
            uv run pytest tests/ -v
        else
            echo "⚠️  No tests found. Skipping test execution."
        fi
        
        echo "🔍 Checking Redis connection..."
        if ! uv run python -c "import redis; r = redis.Redis(host='$REDIS_HOST', port=$REDIS_PORT, password='$REDIS_PASSWORD', db=$REDIS_DB); r.ping(); print('Redis connection successful')" 2>/dev/null; then
            echo "⚠️  Redis connection failed. Please ensure Redis is running and configured correctly."
        fi
        
        echo "🌐 Checking Control Plane connectivity..."
        if ! curl -f -s "$CONTROL_PLANE_URL/health" > /dev/null 2>&1; then
            echo "⚠️  Control Plane not reachable at $CONTROL_PLANE_URL. Agent will retry on startup."
        fi
        ;;
        
    "production")
        echo "🧪 Running unit tests..."
        if [ -f "pytest.ini" ] || [ -d "tests/" ]; then
            uv run pytest tests/unit/ -v --tb=short
        else
            echo "⚠️  No unit tests found. Skipping test execution."
        fi
        
        echo "🔍 Validating Redis connection..."
        if ! uv run python -c "import redis; r = redis.Redis(host='$REDIS_HOST', port=$REDIS_PORT, password='$REDIS_PASSWORD', db=$REDIS_DB); r.ping(); print('Redis connection successful')"; then
            echo "❌ Redis connection failed. Please check your Redis configuration."
            exit 1
        fi
        
        echo "🌐 Validating Control Plane connectivity..."
        if ! curl -f -s "$CONTROL_PLANE_URL/health" > /dev/null 2>&1; then
            echo "❌ Control Plane not reachable at $CONTROL_PLANE_URL. Please check your network configuration."
            exit 1
        fi
        
        echo "🔑 Validating API key..."
        if [ -z "$CONTROL_PLANE_API_KEY" ] || [ "$CONTROL_PLANE_API_KEY" = "your_production_api_key_here" ]; then
            echo "❌ Production API key not configured. Please set CONTROL_PLANE_API_KEY in .env.production"
            exit 1
        fi
        ;;
esac

echo "🎯 Starting FantasiaDataPlaneAgent $ENVIRONMENT server..."
uv run python main.py