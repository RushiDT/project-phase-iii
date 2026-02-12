import asyncio
import logging
import sys

# Configure logging
logging.basicConfig(level=logging.INFO)

try:
    from amqtt.broker import Broker
except ImportError:
    print("\n❌ 'amqtt' library not found.")
    print("👉 Please run: pip install amqtt\n")
    sys.exit(1)

config = {
    'listeners': {
        'default': {
            'type': 'tcp',
            'bind': '0.0.0.0:1883',
        },
    },
    'sys_interval': 10,
    'auth': {
        'allow-anonymous': True,
    }
}

async def start_broker():
    broker = Broker(config)
    await broker.start()
    print("\n✅ Local MQTT Broker started on port 1883")
    print("   Press Ctrl+C to stop.\n")
    while True:
        await asyncio.sleep(1)

if __name__ == '__main__':
    formatter = "[%(asctime)s] :: %(levelname)s :: %(name)s :: %(message)s"
    # logging.basicConfig(level=logging.INFO, format=formatter)
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        asyncio.run(start_broker())
    except KeyboardInterrupt:
        print("\n🛑 Broker stopped.")
