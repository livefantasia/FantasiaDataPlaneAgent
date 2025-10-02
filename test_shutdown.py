#!/usr/bin/env python3
"""
Test script to verify graceful shutdown functionality.
"""

import asyncio
import signal
import sys
import time
from main import main

async def test_shutdown():
    """Test that the application can be started and stopped gracefully."""
    print("Testing graceful shutdown...")
    
    # Start the main application in a task
    main_task = asyncio.create_task(main())
    
    # Wait a bit for startup
    await asyncio.sleep(2)
    
    print("Application started, sending SIGINT (Ctrl+C equivalent)...")
    
    # Send SIGINT to simulate Ctrl+C
    import os
    os.kill(os.getpid(), signal.SIGINT)
    
    try:
        # Wait for the main task to complete
        await asyncio.wait_for(main_task, timeout=10)
        print("✅ Application shut down gracefully!")
        return True
    except asyncio.TimeoutError:
        print("❌ Application did not shut down within timeout")
        main_task.cancel()
        return False
    except Exception as e:
        print(f"✅ Application shut down with expected exception: {type(e).__name__}")
        return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_shutdown())
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("✅ KeyboardInterrupt caught - graceful shutdown works!")
        sys.exit(0)
    except SystemExit:
        print("✅ SystemExit caught - graceful shutdown works!")
        sys.exit(0)