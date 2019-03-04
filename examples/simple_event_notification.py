#!/usr/bin/python3
import os
import time
from settings import login, connection

import trio
import math
from trio_ami import open_ami_client


async def event_notification(source, event):
    print(source,event)


async def main():
    async with open_ami_client(**connection) as client:
        await client.login(**login)
        client.add_event_listener(event_notification)
        print("Connected.")
        trio.sleep(math.inf)

if __name__ == "__main__":
    try:
        trio.run(main)
    except KeyboardInterrupt:
        pass
