"""Main application entry point for DataPlane Agent."""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ApplicationConfig, load_config
from middleware import CorrelationMiddleware
from routers import health_router, metrics_router
from services import (
    CommandProcessor,
    ControlPlaneClient, 
    HealthMetricsService,
    RedisClient,
    RedisConsumerService,
)
from utils import configure_logging, get_logger, initialize_connection_state_manager, set_correlation_id

# Global service instances
config: ApplicationConfig
redis_client: RedisClient
control_plane_client: ControlPlaneClient
redis_consumer: RedisConsumerService
command_processor: CommandProcessor
health_metrics: HealthMetricsService

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management."""
    global config, redis_client, control_plane_client, redis_consumer, command_processor, health_metrics
    
    try:
        # Load configuration - this will fail with detailed error if required vars are missing
        config = load_config()
        logger.info("Configuration loaded successfully", server_id=config.server_id)
    except Exception as e:
        print(f"\n{'='*80}")
        print("CONFIGURATION ERROR: Failed to load application configuration")
        print(f"{'='*80}")
        print(f"Error: {e}")
        print("\nPlease ensure all required environment variables are set in your .env file.")
        print("Check .env.example for a complete list of required variables.")
        print(f"{'='*80}\n")
        sys.exit(1)
    
    # Configure logging with log4j-style format
    # Use JSON output only when explicitly requested (you can add an env var for this)
    json_output = False  # Default to log4j-style format
    configure_logging(config.log_level, json_output=json_output, include_system_context=True)
    
    # Set application-wide correlation ID
    app_correlation_id = set_correlation_id()
    
    # Initialize connection state manager
    initialize_connection_state_manager(config)
    
    logger.info(
        "DataPlane Agent started successfully",
        serviceName="DataPlaneAgent",
        operationName="startup",
        version=config.app_version,
        server_id=config.server_id,
        region=config.server_region,
        debug_mode=config.debug,
        environment="development" if config.debug else "production",
    )
    
    try:
        # Initialize services
        redis_client = RedisClient(config)
        control_plane_client = ControlPlaneClient(config)
        redis_consumer = RedisConsumerService(config, redis_client, control_plane_client)
        command_processor = CommandProcessor(config, redis_client, control_plane_client)
        health_metrics = HealthMetricsService(config, redis_client, control_plane_client)
        
        # Start services
        await redis_client.connect()
        await control_plane_client.start()
        await health_metrics.start()
        await redis_consumer.start()
        await command_processor.start()

        # Store services in app.state for dependency injection
        app.state.health_metrics = health_metrics

        logger.info("All services started successfully")

        yield
        
    except Exception as e:
        logger.error("Failed to start services", error=str(e))
        sys.exit(1)
    
    finally:
        # Cleanup services
        logger.info("Shutting down services")
        
        try:
            await command_processor.stop()
            await redis_consumer.stop()
            await health_metrics.stop()
            await control_plane_client.stop()
            await redis_client.disconnect()
            
            logger.info("All services stopped successfully")
        except Exception as e:
            logger.error("Error during shutdown", error=str(e))


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="DataPlane Agent",
        description="DataPlane Agent for SpeechEngine platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Add correlation ID middleware (before CORS)
    app.add_middleware(CorrelationMiddleware)
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(health_router)
    app.include_router(metrics_router)
    
    return app





# Create the FastAPI app
app = create_app()


async def main() -> None:
    """Main entry point for standalone execution."""
    import uvicorn
    
    try:
        
        # Load config for server settings - this will fail if required vars are missing
        temp_config = load_config()
        
        # Run the server
        server = uvicorn.Server(
            uvicorn.Config(
                app=app,
                host=temp_config.server_host,
                port=temp_config.server_port,
                log_level="warning",  # Suppress uvicorn's info logs
                access_log=False,     # Disable uvicorn access logs (we have our own middleware)
            )
        )
        
        await server.serve()
        
    except Exception as e:
        print(f"\n{'='*80}")
        print("APPLICATION STARTUP ERROR")
        print(f"{'='*80}")
        print(f"Error: {e}")
        print("\nPlease check your configuration and ensure all required environment variables are set.")
        print("See .env.example for a complete list of required variables.")
        print(f"{'='*80}\n")
        sys.exit(1)


if __name__ == "__main__":
    # Use asyncio.run for proper signal handling when running directly
    asyncio.run(main())
