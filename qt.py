from typing import Callable

import parallel
import threading
from PyQt5 import QtWidgets, QtCore
import time

CMD_SHOW_MSG = (0, 1)  # (title, text) -> result
CMD_SHOW_QUESTION = (2, 3)  # (title, text, [opt] options) -> result
CMD_OPEN_PROGRESS = (4, 5)  # (title, text, range) -> handle
CMD_UPDATE_PROGRESS = (6, 7)  # (handle, value) -> None
CMD_CLOSE_PROGRESS = (8, 9)  # (handle) -> None


def _bring_to_front(window):
    window.setWindowFlags(window.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
    window.show()
    # maybe clearing is unnecessary, depends on the way you want it to act
    window.setWindowFlags(window.windowFlags() & ~QtCore.Qt.WindowStaysOnTopHint)
    window.show()


class QtThread:
    def __init__(self):
        self._channel = parallel.CommandChannel()
        self._worker = threading.Thread(target=self._work)
        self._worker.daemon = True
        self._app = None
        self._timer = None
        self._running = False

        self._add_handler(*CMD_SHOW_MSG, self._on_show_msg)
        self._add_handler(*CMD_SHOW_QUESTION, self._on_show_question)


    @property
    def channel(self):
        return self._channel

    @property
    def running(self):
        return self._running

    def start(self):
        if not self.running:
            self._worker.start()
            while not self._running:
                time.sleep(0.1)

    def _add_handler(self, cmd, cmd_result, handler: Callable[["parallel.CommandAction"], None]):
        self.channel.receiver.register(cmd, cmd_result, handler)

    def _work(self):
        self._running = True
        self._app = QtWidgets.QApplication([])
        while self.running:
            self.channel.receiver.handle_invocations()
            time.sleep(0.1)

        print("app exit")
        self._running = False

    def _on_show_msg(self, action: "parallel.CommandAction"):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle(action.parameter[0])
        msg.setText(action.parameter[1])
        _bring_to_front(msg)
        self._app.exec_()
        action.finish(msg.result())

    def _on_show_question(self, action: "parallel.CommandAction"):
        msg = QtWidgets.QMessageBox()
        msg.setWindowTitle(action.parameter[0])
        msg.setText(action.parameter[1])
        msg.setIcon(QtWidgets.QMessageBox.Question)
        if len(action.parameter) > 2:
            msg.setStandardButtons(action.parameter[2])
        _bring_to_front(msg)
        self._app.exec_()
        action.finish(msg.result())

