#!/usr/bin/python3
import os
import time
from settings import login, connection

import anyio
import math
from asyncami import open_ami_client


async def event_notification(source, event):
    print(source,event)


async def main():
    async with open_ami_client(**connection) as client:
        await client.login(**login)
        client.add_event_listener(event_notification)
        print("Connected.")
        await anyio

if __name__ == "__main__":
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        pass
