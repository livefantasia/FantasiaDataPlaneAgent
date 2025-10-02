#!/usr/bin/env python3
"""
Manual test script to verify Ctrl+C behavior.
Run this script and press Ctrl+C to test graceful shutdown.
"""

import asyncio
import signal
import sys

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        print(f"\n✅ Received signal {signum} (Ctrl+C), shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

async def main():
    """Main function that mimics the application behavior."""
    setup_signal_handlers()
    
    print("🚀 Test server starting...")
    print("📝 Press Ctrl+C to test graceful shutdown")
    print("⏳ Waiting for signal...")
    
    try:
        # Simulate the server running
        while True:
            await asyncio.sleep(1)
            print(".", end="", flush=True)
    except KeyboardInterrupt:
        print("\n✅ KeyboardInterrupt caught - graceful shutdown works!")
    except SystemExit:
        print("\n✅ SystemExit caught - graceful shutdown works!")
    finally:
        print("🛑 Cleanup completed")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ Final KeyboardInterrupt caught - graceful shutdown works!")
    except SystemExit:
        print("\n✅ Final SystemExit caught - graceful shutdown works!")
    
    print("🎉 Test completed successfully!")