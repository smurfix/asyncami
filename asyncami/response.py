import re
import anyio
import outcome

class Response(object):
    match_regex = re.compile('^Response: .*', re.IGNORECASE)
    key_regex = re.compile('^[a-zA-Z0-9_\-]+$')

    @staticmethod
    def read(response):
        lines = response.splitlines()
        (key, value) = map(lambda s: s.strip(), lines[0].split(':', 1))
        if not key.lower() == 'response':
            raise Exception()
        status = value
        keys = {}
        follows = [] if status.lower() == 'follows' else None
        keys_and_follows = iter(lines[1:])
        for line in keys_and_follows:
            try:
                (key, value) = line.split(':', 1)
                if not Response.key_regex.match(key):
                    raise key
                keys[key.strip()] = value.strip()
            except:
                if follows is not None:
                    follows.append(line)
                break
        if follows is not None:
            for line in keys_and_follows:
                follows.append(line)
        return Response(status, keys, follows)

    @staticmethod
    def match(response):
        return bool(Response.match_regex.match(response))

    def __init__(self, status, keys={}, fallows=None):
        self.status = status
        self.keys = keys
        self.follows = fallows

    def __str__(self):
        package = 'Response: %s\r\n' % self.status
        for key in self.keys:
            package += '%s: %s\r\n' % (key, self.keys[key])
        if self.follows is not None and len(self.follows) > 0:
            package += '\r\n'.join(self.follows) + '\r\n'
        return package

    def is_error(self):
        return self.status.lower() == 'error'

class Future:
    """A waitable value useful for inter-task synchronization.

    An event object manages an internal value, which is initially
    unset, and a task can wait for it to become True.

    Args:
      ``scope``:  A cancelation scope that will be cancelled if/when
                  this ValueEvent is. Used for clean cancel propagation.

    Note that the value can only be read once.
    """

    def __init__(self, scope=None):
        self.value = None
        self.event = anyio.create_event()
        self.scope = scope

    async def set(self, value=None):
        """Set the result to return this value, and wake any waiting task.
        """
        if self.value is not None:
            raise RuntimeError("already set")
        self.value = outcome.Value(value)
        await self.event.set()

    async def set_error(self, exc):
        """Set the result to raise this exceptio, and wake any waiting task.
        """
        if self.value is not None:
            raise RuntimeError("already set")
        self.value = outcome.Error(exc)
        await self.event.set()

    def is_set(self):
        """Check whether the event has occurred.
        """
        return self.value is not None

    async def cancel(self):
        """Send a cancelation to the recipient.

        TODO: anyio can't do that cleanly.
        """
        if self.scope is not None:
            await self.scope.cancel()
        return await self.set_error(CancelledError())

    async def get(self):
        """Block until the value is set.

        If it's already set, then this method returns immediately.

        The value can only be read once.
        """
        await self.event.wait()
        return self.value.unwrap()

    def __await__(self):
        return self.get().__await__()

