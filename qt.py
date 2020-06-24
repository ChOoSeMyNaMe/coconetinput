import parallel
import threading
from PyQt5 import QtWidgets, QtCore
import time

CMD_SHOW_MSG = (0, 1)


class QtThread:
    def __init__(self):
        self._channel = parallel.CommandChannel()
        self._worker = threading.Thread(target=self._work)
        self._app = None
        self._timer = None
        self._running = False

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

    def _work(self):
        self._running = True
        self._app = QtWidgets.QApplication([])
        while self.running:
            self._check_commands()
            time.sleep(0.1)

        print("app exit")
        self._running = False

    def _check_commands(self):
        action = self.channel.receiver.invoked(*CMD_SHOW_MSG)
        if action:
            msg = QtWidgets.QMessageBox()
            msg.setWindowTitle(action.parameter[0])
            msg.setText(action.parameter[1])
            msg.show()
            self._app.exec_()
            result = msg.result()
            action.finish()
