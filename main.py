"""Main application entry point for DataPlane Agent."""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from concurrent.futures import ThreadPoolExecutor

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
from utils import configure_logging, get_logger, set_correlation_id


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management for the new threaded architecture."""
    config = load_config()
    configure_logging(config.log_level, json_output=False)
    logger = get_logger(__name__)
    set_correlation_id()

    # Use a ThreadPoolExecutor for all synchronous, blocking tasks
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="agent_worker")
    
    # Initialize all services
    redis_client = RedisClient(config)
    control_plane_client = ControlPlaneClient(config)
    redis_consumer = RedisConsumerService(config, redis_client, control_plane_client) # This service remains async
    health_metrics = HealthMetricsService(config, redis_client, control_plane_client, executor)
    command_processor = CommandProcessor(config, redis_client, control_plane_client, executor)

    try:
        logger.info("Starting services...")
        await redis_client.connect()
        
        # Start the synchronous workers in the background thread pool
        health_metrics.start()
        command_processor.start()

        # Start the async consumer tasks
        await redis_consumer.start()

        # Pass services to the app state if needed by request handlers
        app.state.health_metrics = health_metrics
        logger.info("All services are running.")

        yield

    finally:
        logger.info("Shutting down services...")
        
        # Stop the async consumers first
        await redis_consumer.stop()

        # Signal the sync workers to stop
        command_processor.stop()
        health_metrics.stop()

        # Shut down the thread pool, waiting for workers to finish
        logger.info("Shutting down thread pool...")
        executor.shutdown(wait=True)
        logger.info("Thread pool shut down.")

        await redis_client.disconnect()
        logger.info("All services stopped successfully.")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="DataPlane Agent",
        description="DataPlane Agent for SpeechEngine platform",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(metrics_router)
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    config = load_config()
    uvicorn.run(app, host=config.server_host, port=config.server_port)
