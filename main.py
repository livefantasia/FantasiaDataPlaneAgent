"""Main application entry point for DataPlane Agent."""

import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import ApplicationConfig, load_config
from routers import health_router, metrics_router
from services import (
    CommandProcessor,
    ControlPlaneClient, 
    HealthMetricsService,
    RedisClient,
    RedisConsumerService,
)
from utils import configure_logging, get_logger

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
    
    # Load configuration
    config = load_config()
    
    # Configure logging
    configure_logging(config.log_level)
    
    logger.info(
        "Starting DataPlane Agent",
        version=config.app_version,
        server_id=config.server_id,
        region=config.server_region,
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


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, initiating shutdown")
        # FastAPI will handle the shutdown through lifespan context manager
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


# Create the FastAPI app
app = create_app()


async def main() -> None:
    """Main entry point for standalone execution."""
    import uvicorn
    
    setup_signal_handlers()
    
    # Load config for server settings
    temp_config = load_config()
    
    # Run the server
    server = uvicorn.Server(
        uvicorn.Config(
            app=app,
            host=temp_config.server_host,
            port=temp_config.server_port,
            log_level=temp_config.log_level.lower(),
            access_log=True,
        )
    )
    
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
