from typing import Callable, Dict

from PyQt5 import QtWidgets
from PyQt5.QtCore import QSettings

import qt
import os
import threading
import easyprocess
import time
import watchdog.observers
import watchdog.events
import coconet
import pretty_midi as midi
import mido
import sys

EDITOR_PATH = r"D:\Temp\MidiEditor\MidiEditor.exe"

GUI_THREAD: qt.QtThread = None
COCONET_PROCESS: coconet.CoconetJob = None
MIDI_IN: str = None
MIDI_OUT: str = None

EDITOR_KEY_PORT_IN = "in_port"
EDITOR_KEY_PORT_OUT = "out_port"
EDITOR_KEY_CONNECT_PORTS = "thru"

def get_int_from_args(index: int) -> int:
    if len(sys.argv) > index:
        try:
            return int(sys.argv[index])
        except Exception:
            pass
    return -1


def get_midi_input() -> str:
    names = mido.get_input_names()
    if len(names) == 0:
        print("No MIDI-Input devices available.")
        exit(1)

    index = get_int_from_args(1)
    if index >= 0 and index < len(names):
        print("Using", names[index], "as input device")
        return names[index]

    print("Please select an MIDI-Input device:")
    for i, name in enumerate(names):
        print(f"[{i}]: {name}")
    index = -1
    while index < 0 or index >= len(names):
        try:
            index = int(input("Device-Index: "))
        except Exception:
            index = -1
            print("Invalid format.")
    return names[index]


def get_midi_output() -> str:
    names = mido.get_output_names()
    if len(names) == 0:
        print("No MIDI-Output devices available.")
        exit(1)

    index = get_int_from_args(2)
    if index >= 0 and index < len(names):
        print("Using", names[index], "as output device")
        return names[index]

    print("Please select an MIDI-Output device:")
    for i, name in enumerate(names):
        print(f"[{i}]: {name}")
    index = -1
    while index < 0 or index >= len(names):
        try:
            index = int(input("Device-Index: "))
        except Exception:
            index = -1
            print("Invalid format.")
    return names[index]


def create_empty_mid(name: str) -> str:
    path = os.path.join(os.getcwd(), name)
    tmp = midi.PrettyMIDI()
    tmp.write(path)
    print("[main]: Created empty MIDI at", path)
    return path


def run_editor_input() -> "Editor":
    editor = Editor(create_empty_mid("output.mid"))
    editor.ensure_setting(EDITOR_KEY_PORT_IN, MIDI_IN)
    editor.ensure_setting(EDITOR_KEY_PORT_OUT, MIDI_OUT)
    editor.ensure_setting(EDITOR_KEY_CONNECT_PORTS, True)
    editor.start()
    return editor

def run_editor_output(file) -> "Editor":
    editor = Editor(file, False)
    editor.ensure_setting(EDITOR_KEY_PORT_IN, "")
    editor.ensure_setting(EDITOR_KEY_PORT_OUT, MIDI_OUT)
    editor.ensure_setting(EDITOR_KEY_CONNECT_PORTS, False)
    editor.start()
    return editor

class Editor:
    def __init__(self, midi_path: str, restart: bool=True):
        self.restart = restart
        self.running = False
        self.process: easyprocess.EasyProcess = None
        self.worker = threading.Thread(target=self._work)
        self.path = midi_path
        self._settings: QSettings = None
        self._ensured_settings: Dict[str, any] = dict()
        print("[MidiEditor]: Opening MIDI at", self.path)

    def ensure_setting(self, key: str, value: any):
        self._ensured_settings[key] = value

    def _ensure_settings(self):
        print("[MidiEditor]: Ensuring correct settings...")
        self._load_settings()
        for key, value in self._ensured_settings.items():
            self._settings.setValue(key, value)
        self._settings.sync()

    def _load_settings(self):
        if self._settings is None:
            self._settings = QSettings("MidiEditor", "NONE")

    def _work(self):
        self._ensure_settings()
        self.process = easyprocess.EasyProcess([EDITOR_PATH, self.path])
        print("[MidiEditor]: Starting...")
        self.process.start()
        print("[MidiEditor]: Started...")
        while self.running:
            if self.running and self.restart and not self.process.is_alive():
                print("[MidiEditor]: Exited unexpectedly. Restarting...")
                self._ensure_settings()
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
        file = os.path.join(os.getcwd(), "batch.mid")
        result[0].write(file)

        print("[FileObserver]: Opening editor...")
        run_editor_output(file)

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
    editor = run_editor_input()

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
    MIDI_IN = get_midi_input()
    MIDI_OUT = get_midi_output()
    main()
