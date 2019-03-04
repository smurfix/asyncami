import re
import trio
import socket
from outcome import capture
from functools import partial
from async_generator import asynccontextmanager

from .action import Action, LoginAction, LogoffAction, SimpleAction
from .event import Event, EventListener
from .response import Response, FutureResponse

try:
    unicode = unicode
except NameError:
    str = str
    unicode = str
    bytes = bytes
    basestring = (str, bytes)
else:
    str = str
    unicode = unicode
    bytes = str
    basestring = basestring

NOOP = lambda *args, **kwargs: None

NOOP_LISTENER = dict(
    on_action=NOOP,
    on_response=NOOP,
    on_event=NOOP,
    on_connect=NOOP,
    on_disconnect=NOOP,
    on_unknown=NOOP,
)


class AMIClientListener(object):
    methods = ['on_action', 'on_response', 'on_event', 'on_connect', 'on_disconnect', 'on_unknown']

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k not in self.methods:
                raise TypeError('\'%s\' is an invalid keyword argument for this function' % k)
            setattr(self, k, v)

    def on_action(self, source, action):
        raise NotImplementedError()

    def on_response(self, source, response):
        raise NotImplementedError()

    def on_event(self, source, event):
        raise NotImplementedError()

    def on_connect(self, source):
        raise NotImplementedError()

    def on_disconnect(self, source, error=None):
        raise NotImplementedError()

    def on_unknown(self, source, pack):
        raise NotImplementedError()


@asynccontextmanager
async def open_ami_client(*args, **kwargs):
    async with trio.open_nursery() as n:
        client = AMIClient(*args, _nursery=n, **kwargs)
        try:
            # await client.connect()
            yield client
        finally:
            await client.aclose()

class AMIClient(object):
    asterisk_start_regex = re.compile('^Asterisk *Call *Manager/(?P<version>([0-9]+\.)*[0-9]+)', re.IGNORECASE)
    asterisk_line_regex = re.compile(b'\r\n', re.IGNORECASE | re.MULTILINE)
    asterisk_pack_regex = re.compile(b'\r\n\r\n', re.IGNORECASE | re.MULTILINE)

    def __init__(self, address='127.0.0.1', port=5038,
                 encoding='utf-8', timeout=3, buffer_size=2 ** 10,
                 _nursery=None, **kwargs):
        self._action_counter = 0
        self._futures = {}
        self._listeners = []
        self._event_listeners = []
        self._address = address
        self._buffer_size = buffer_size
        self._port = port
        self._socket = None
        self.finished = None
        self._ami_version = None
        self._timeout = timeout
        self._nursery = _nursery
        self.encoding = encoding
        if len(kwargs) > 0:
            self.add_listener(**kwargs)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *tb):
        await self.aclose()

    def next_action_id(self):
        id = self._action_counter
        self._action_counter += 1
        return str(id)

    async def connect(self):
        if self._socket is not None:
            raise RuntimeError("alrady connected")
        try:
            with trio.fail_after(self._timeout):
                self._socket = await trio.open_tcp_stream(self._address, self._port)
        except BaseException:
            if self._socket is not None:
                with trio.open_cancel_scope(shield=True):
                    await self._socket.aclose()
                self._socket = None
                raise

        self.finished = trio.Event()
        await self._nursery.start(self.listen)

    async def _fire_on_connect(self, **kwargs):
        for listener in self._listeners:
            await listener.on_connect(source=self, **kwargs)

    async def _fire_on_disconnect(self, **kwargs):
        for listener in self._listeners:
            await listener.on_disconnect(source=self, **kwargs)

    async def _fire_on_response(self, **kwargs):
        for listener in self._listeners:
            await listener.on_response(source=self, **kwargs)

    async def _fire_on_action(self, **kwargs):
        for listener in self._listeners:
            await listener.on_action(source=self, **kwargs)

    async def _fire_on_event(self, **kwargs):
        for listener in self._listeners:
            await listener.on_event(source=self, **kwargs)

    async def _fire_on_unknown(self, **kwargs):
        for listener in self._listeners:
            await listener.on_unknown(source=self, **kwargs)

    async def aclose(self):
        if self.finished is not None:
            self.finished.set()
        try:
            await self._socket.aclose()
        except Exception:
            pass

    async def login(self, username, secret):
        if self.finished is None or self.finished.is_set():
            await self.connect()
        return await self.send_action(LoginAction(username, secret))

    async def logoff(self):
        if self.finished is None or self.finished.is_set():
            return
        return await self.send_action(LogoffAction())

    async def send_action(self, action):
        if 'ActionID' not in action.keys:
            action_id = self.next_action_id()
            action.keys['ActionID'] = action_id
        else:
            action_id = action.keys['ActionID']
        evt = trio.Event()
        future = FutureResponse(callback, self._timeout)
        self._futures[action_id] = evt
        self._fire_on_action(action=action)
        await self.send(action)
        await evt.wait()

        return result.unwrap()

    async def send(self, pack):
        await self._socket.send_all(bytearray(str(pack) + '\r\n', self.encoding))

    def _decode_pack(self, pack):
        return pack.decode(self.encoding)

    async def _next_pack(self):
        data = b''
        regex = self.asterisk_line_regex
        while not self.finished.is_set():
            recv = await self._socket.receive_some(self._buffer_size)
            if recv == b'':
                self.finished.set()
                continue
            data += recv
            while regex.search(data):
                (pack, data) = self.asterisk_line_regex.split(data, 1)
                yield self._decode_pack(pack)
                regex = self.asterisk_pack_regex
        self._socket.close()

    async def listen(self, task_status=trio.TASK_STATUS_IGNORED):
        pack_generator = self._next_pack()
        asterisk_start = await pack_generator.__anext__()
        match = AMIClient.asterisk_start_regex.match(asterisk_start)
        if not match:
            raise Exception()
        self._ami_version = match.group('version')
        await self._fire_on_connect()
        task_status.started()
        try:
            while not self.finished.is_set():
                pack = pack_generator.__anext__()
                await self.fire_recv_pack(pack)
            self._fire_on_disconnect(error=None)
        except Exception as ex:
            await self._fire_on_disconnect(error=ex)

    async def fire_recv_reponse(self, response):
        await self._fire_on_response(response=response)
        if response.status.lower() == 'goodbye':
            self.finished.set()
        if 'ActionID' not in response.keys:
            return
        action_id = response.keys['ActionID']
        if action_id not in self._futures:
            return
        event = self._futures[action_id]
        self._futures[action_id] = response
        event.set()

    async def fire_recv_event(self, event):
        self._fire_on_event(event=event)
        for listener in self._event_listeners:
            await listener(event=event, source=self)

    async def fire_recv_pack(self, pack):
        if Response.match(pack):
            response = Response.read(pack)
            await self.fire_recv_reponse(response)
            return
        if Event.match(pack):
            event = Event.read(pack)
            await self.fire_recv_event(event)
            return
        await self._fire_on_unknown(pack=pack)

    def add_listener(self, listener=None, **kwargs):
        if not listener:
            default = NOOP_LISTENER.copy()
            default.update(kwargs)
            listener = AMIClientListener(**default)
        self._listeners.append(listener)
        return listener

    def remove_listener(self, listener):
        self._listeners.remove(listener)
        return listener

    def add_event_listener(self, on_event=None, **kwargs):
        if len(kwargs) > 0 and not isinstance(on_event, EventListener):
            event_listener = EventListener(on_event=on_event, **kwargs)
        else:
            event_listener = on_event
        self._event_listeners.append(event_listener)
        return event_listener

    def remove_event_listener(self, event_listener):
        self._event_listeners.remove(event_listener)


class AMIClientAdapter(object):
    def __init__(self, ami_client):
        self._ami_client = ami_client

    def _action(self, name, _callback=None, variables={}, **kwargs):
        action = Action(name, kwargs)
        action.variables = variables
        return self._ami_client.send_action(action, _callback)

    def __getattr__(self, item):
        return partial(self._action, item)

async def _ignore(*args):
    pass

class AutoReconnect:
    def __init__(self, ami_client, delay=0.5,
                 on_disconnect=_ignore, on_reconnect=_ignore):
        super(AutoReconnect, self).__init__()
        self.on_reconnect = on_reconnect
        self.on_disconnect = on_disconnect
        self.delay = delay
        self.finished = None
        self._ami_client = ami_client
        self._login_args = None
        self._login = None
        self._logoff = None

    def _prepare_client(self):
        self._login = self._ami_client.login
        self._logoff = self._ami_client.logoff
        self._ami_client.login = self._login_wrapper
        self._ami_client.logoff = self._logoff_wrapper

    def _rollback_client(self):
        self._ami_client.login = self._login
        self._ami_client.logoff = self._logoff

    async def _login_wrapper(self, *args, **kwargs):
        response = await self._login(*args, **kwargs)
        if not response.is_error():
            if self._login_args is None:
                self.finished = trio.Event()
                await self._ami_client._nursery.start(self.run)
            self._login_args = (args, kwargs)

        kwargs['callback'] = on_login

    async def _logoff_wrapper(self, *args, **kwargs):
        self.finished.set()
        self._rollback_client()
        return await self._logoff(*args, **kwargs)

    async def ping(self):
        try:
            response = await self._ami_client.send_action(Action('Ping'))
            if response is not None and not response.is_error():
                return True
            await self.on_disconnect(self._ami_client, response)
        except Exception as ex:
            await self.on_disconnect(self._ami_client, ex)
        return False

    async def try_reconnect(self):
        try:
            f = self._login(*self._login_args[0], **self._login_args[1])
            response = f.response
            if response is not None and not response.is_error():
                await self.on_reconnect(self._ami_client, response)
                return True
        except Exception:
            pass
        return False

    async def run(self, task_status=trio.TASK_STATUS_IGNORED):
        self._prepare_client()
        task_status.started()
        try:
            while not self.finished.is_set():
                with trio.move_on_after(self.delay):
                    await self.finished.wait()
                if not await self.ping():
                    await self.try_reconnect()
        finally:
            self._rollback_client()

