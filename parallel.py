import queue
import multiprocessing
from abc import ABC, abstractmethod
from typing import Tuple, Union, Callable, List


class CommandException(Exception):
    def __init__(self, cmd, msg):
        super(CommandException, self).__init__(f"Command {cmd}: {msg}")
        self.cmd = cmd
        self.msg = msg


class CommandAction:
    def __init__(self, owner: "ChannelActor", cmd, parameter, return_cmd):
        self._cmd = cmd
        self._owner = owner
        self._parameter = parameter
        self._return_cmd = return_cmd

    @property
    def parameter(self):
        return self._parameter

    def fail(self, msg):
        self.finish(CommandException(self._cmd, msg))

    def fail_nowait(self, msg):
        self.finish_nowait(CommandException(self._cmd, msg))

    def finish(self, value=None):
        self._owner.send(self._return_cmd, value)

    def finish_nowait(self, value=None):
        self._owner.send_nowait(self._return_cmd, value)


class InvocationHandler:
    def __init__(self, cmd, cmd_result, handler: Callable[["CommandAction"], None]):
        self.handler = handler
        self.cmd_result = cmd_result
        self.cmd = cmd

    def process(self, actor: "ChannelActor") -> bool:
        action = actor.invoked(self.cmd, self.cmd_result)
        if action:
            self.handler(action)
            return True
        return False

    def __eq__(self, other):
        if isinstance(other, InvocationHandler):
            return self.cmd == other.cmd and self.cmd_result == other.cmd_result
        return False


class ChannelActor:
    def __init__(self, send: Union[queue.Queue, multiprocessing.Queue],
                 receive: Union[queue.Queue, multiprocessing.Queue]):
        self._send = send
        self._receive = receive
        self._handlers: List["InvocationHandler"] = []

    def register(self, cmd, cmd_result, handler: Callable[["CommandAction"], None]):
        item = InvocationHandler(cmd, cmd_result, handler)
        if item not in self._handlers:
            self._handlers.append(item)

    def unregister(self, cmd, cmd_result):
        remove = None
        for item in self._handlers:
            if item.cmd == cmd and item.cmd_result == cmd_result:
                remove = item
                break
        if remove is not None:
            self._handlers.remove(remove)

    def send(self, cmd, value):
        self._send.put((cmd, value))

    def send_nowait(self, cmd, value) -> bool:
        try:
            self._send.put_nowait((cmd, value))
            return True
        except queue.Full:
            return False

    def receive(self) -> Tuple[any, any]:
        return self._receive.get()

    def receive_nowait(self) -> Union[Tuple[any, any], None]:
        try:
            return self._receive.get_nowait()
        except queue.Empty:
            return None

    def receive_value(self, cmd) -> any:
        result = self.receive()
        while result[0] != cmd:
            self._receive.put(result)
            result = self.receive()
        return result[1]

    def receive_value_failing(self, cmd) -> any:
        result = self.receive_value(cmd)
        if isinstance(result, CommandException):
            raise result
        else:
            return result

    def received_cmd(self, cmd) -> bool:
        result = self.receive_nowait()
        if result is not None:
            if result[0] == cmd:
                return True
            else:
                self._receive.put_nowait(result)
        return False

    def received_cmd_value(self, cmd) -> Tuple[bool, any]:
        result = self.receive_nowait()
        if result is not None:
            if result[0] == cmd:
                return True, result[1]
            else:
                self._receive.put_nowait(result)
        return False, None

    def clear_all(self, cmd):
        while self.received_cmd(cmd):
            pass

    def invoke(self, cmd, result_cmd, value=None) -> any:
        self.send(cmd, value)
        return self.receive_value(result_cmd)

    def invoke_failing(self, cmd, result_cmd, value=None) -> any:
        self.send(cmd, value)
        return self.receive_value_failing(result_cmd)

    def invoked(self, cmd, result_cmd) -> Union["CommandAction", None]:
        result = self.received_cmd_value(cmd)
        if result[0]:
            return CommandAction(self, cmd, result[1], result_cmd)
        return None

    def handle_invocations(self):
        for handler in self._handlers:
            handler.process(self)


class CommandChannel:
    def __init__(self, is_process: bool = False):
        self._send = queue.Queue() if not is_process else multiprocessing.Queue()
        self._receive = queue.Queue() if not is_process else multiprocessing.Queue()
        self._sender = ChannelActor(self._send, self._receive)
        self._receiver = ChannelActor(self._receive, self._send)

    @property
    def send_queue(self):
        return self._send

    @property
    def receive_queue(self):
        return self._receive

    @property
    def sender(self) -> "ChannelActor":
        return self._sender

    @property
    def receiver(self) -> "ChannelActor":
        return self._receiver


class ParallelJob(multiprocessing.Process, ABC):
    def _run(self, send_queue: multiprocessing.Queue, receive_queue: multiprocessing.Queue):
        actor = ChannelActor(receive_queue, send_queue)
        self.work(actor)

    @property
    def channel(self):
        return self._channel

    def __init__(self):
        self._channel = CommandChannel(True)
        super().__init__(target=self._run, args=(self._channel.send_queue, self._channel.receive_queue))

    @abstractmethod
    def work(self, receiver: "ChannelActor"):
        pass
