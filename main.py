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
import coconet
import pretty_midi as midi

EDITOR_PATH = r"D:\Temp\MidiEditor\MidiEditor.exe"

GUI_THREAD: qt.QtThread = None
COCONET_PROCESS: coconet.CoconetJob = None


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
        print("[MidiEditor]: Created empty MIDI at", self.path)

    def _work(self):
        self.process = easyprocess.EasyProcess([EDITOR_PATH, self.path])
        print("[MidiEditor]: Starting...")
        self.process.start()
        print("[MidiEditor]: Started...")
        while self.running:
            if self.running and not self.process.is_alive():
                print("[MidiEditor]: Exited unexpectedly. Restarting...")
                self.process = easyprocess.EasyProcess([EDITOR_PATH, self.path])
                self.process.start()
            time.sleep(0.1)
        print("[MidiEditor]: Exiting...")
        if self.process.is_alive():
            self.process.stop()
        print("[MidiEditor]: Exited...")

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
    print("[FileObserver]: File changed.")
    result = GUI_THREAD.channel.sender.invoke(
        *qt.CMD_SHOW_QUESTION,
        (
            "File changed",
            "Do you want to generate the remaining voices?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
    )

    if result == QtWidgets.QMessageBox.Yes:
        print("[FileObserver]: Opening Progressdialog...")
        GUI_THREAD.channel.sender.invoke(
            *qt.CMD_OPEN_PROGRESS, ("Generating", "Generating voices...", (0, 0))
        )

        print("[FileObserver]: Sending MIDI to Coconet...")
        midi_in = midi.PrettyMIDI(path)
        result = COCONET_PROCESS.channel.sender.invoke(
            *coconet.CMD_GENERATE, midi_in
        )

        print("[FileObserver]: Saving results...")
        for i, midi_out in enumerate(result):
            midi_out.write(f"batch{i}.mid")

        print("[FileObserver]: Closing Progressdialog...")
        GUI_THREAD.channel.sender.invoke(*qt.CMD_CLOSE_PROGRESS)


def main():
    global GUI_THREAD, COCONET_PROCESS

    print("[main]: Starting Coconet-Process...")
    COCONET_PROCESS = coconet.CoconetJob()
    COCONET_PROCESS.start()

    print("[main]: Loading model in Coconet...")
    COCONET_PROCESS.channel.sender.invoke_failing(*coconet.CMD_LOAD, "pretrained")

    print("[main]: Checking state of Coconet...")
    if not COCONET_PROCESS.channel.sender.invoke(*coconet.CMD_STATE) == coconet.STATE_LOADED:
        print("[main]: Invalid state.")
        exit(-1)

    print("[main]: Starting MidiEditor...")
    editor = run_editor()

    print("[main]: Starting FileObserver...")
    observer = watchdog.observers.Observer()
    handler = FileWatcher(editor.path, on_change)
    observer.schedule(handler, ".")
    observer.start()

    print("[main]: Starting GUI...")
    GUI_THREAD = qt.QtThread()
    GUI_THREAD.start()

    print("[main]: Ready. Press any key to exit the program.")
    input()

    print("[main]: Shutting down Coconet...")
    COCONET_PROCESS.shutdown()

    print("[main]: Shutting FileObserver...")
    observer.stop()
    observer.join()

    print("[main]: Shutting MidiEditor...")
    editor.stop()
    editor.worker.join()


if __name__ == '__main__':
    main()
