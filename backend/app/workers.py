# For this prototype we rely on FastAPI BackgroundTasks to run generation tasks.
# This module can be expanded to include a dedicated queue or scheduler.

import asyncio

# Placeholder file to add worker utilities later.

async def dummy_worker():
    while False:
        await asyncio.sleep(1)
