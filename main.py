from typing import Callable

from PyQt5 import QtWidgets

import qt
import pretty_midi as midi
import os
import threading
import easyprocess
import time
import watchdog.observers
import watchdog.events

EDITOR_PATH = r"D:\Temp\MidiEditor\MidiEditor.exe"

GUI_THREAD = None

def create_empty_mid(name: str) -> str:
    path = os.path.join(os.getcwd(), name)
    tmp = midi.PrettyMIDI()
    tmp.write(path)
    return path


def run_editor() -> "Editor":
    editor = Editor()
    editor.start()
    return editor

class Editor:
    def __init__(self):
        self.running = False
        self.process: easyprocess.EasyProcess = None
        self.worker = threading.Thread(target=self._work)
        self.path = create_empty_mid("output.mid")

    def _work(self):
        self.process = easyprocess.EasyProcess([EDITOR_PATH, self.path])
        self.process.start()
        while self.running:
            if self.running and not self.process.is_alive():
                print("Restarting")
                self.process = easyprocess.EasyProcess([EDITOR_PATH, self.path])
                self.process.start()
            time.sleep(0.1)
        if self.process.is_alive():
            self.process.stop()


    def start(self):
        if not self.running:
            self.running = True
            self.worker.start()

    def stop(self):
        self.running = False


class FileWatcher(watchdog.events.FileSystemEventHandler):
    def __init__(self, path: str, action: Callable):
        self.action = action
        self.path = path
        self._called = False

    def on_modified(self, event):
        super().on_modified(event)
        if isinstance(event, watchdog.events.FileModifiedEvent):
            path = os.path.abspath(event.src_path)
            if path == self.path:
                if not self._called:
                    self.action(path)
                    self._called = True
                else:
                    self._called = False

def on_change(path: str):
    print("Changed")
    GUI_THREAD.channel.sender.invoke(*qt.CMD_SHOW_MSG, ("Test", "hello"))

def main():
    global GUI_THREAD
    editor = run_editor()
    observer = watchdog.observers.Observer()
    handler = FileWatcher(editor.path, on_change)
    observer.schedule(handler, ".")
    observer.start()
    GUI_THREAD = qt.QtThread()
    GUI_THREAD.start()
    input()
    observer.stop()
    editor.stop()
    observer.join()
    editor.worker.join()



if __name__ == '__main__':
    main()
