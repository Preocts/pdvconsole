"""
MIT License

Copyright (c) 2021 Simon D. Levy

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Sourced: https://github.com/simondlevy/kbhit

A Python class implementing KBHIT, the standard keyboard-interrupt poller.
Works transparently on Windows and Posix (Linux, Mac OS X).  Doesn't work
with IDLE.

Copyright (c) 2021 Simon D. Levy

MIT License
"""
from __future__ import annotations

import sys
import threading
from collections.abc import Callable

# Windows
if sys.platform == "win32":
    import msvcrt

# Posix (Linux, OS X)
else:
    import sys
    import termios
    import atexit
    from select import select


class _KBHit:
    def __init__(self) -> None:
        """Creates a KBHit object that you can call to do various keyboard things."""

        if sys.platform == "win32":
            pass

        else:
            # Save the terminal settings
            self.fd = sys.stdin.fileno()
            self.new_term = termios.tcgetattr(self.fd)
            self.old_term = termios.tcgetattr(self.fd)

            # New terminal setting unbuffered
            self.new_term[3] = self.new_term[3] & ~termios.ICANON & ~termios.ECHO
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.new_term)

            # Support normal-terminal reset at exit
            atexit.register(self.set_normal_term)

    def set_normal_term(self) -> None:
        """Resets to normal terminal.  On Windows this is a no-op."""
        if sys.platform != "win32":
            termios.tcsetattr(self.fd, termios.TCSAFLUSH, self.old_term)

    def getch(self) -> str:
        """Returns a keyboard character after kbhit() has been called.
        Should not be called in the same program as getarrow().
        """
        if sys.platform == "win32":
            return msvcrt.getch().decode("utf-8")

        else:
            return sys.stdin.read(1)

    def getarrow(self) -> int:
        """Returns an arrow-key code after kbhit() has been called. Codes are
        0 : up
        1 : right
        2 : down
        3 : left
        Should not be called in the same program as getch().
        """
        if sys.platform == "win32":
            msvcrt.getch()  # skip 0xE0
            c = msvcrt.getch().decode("utf-8")
            vals = [72, 77, 80, 75]

        else:
            c = sys.stdin.read(3)[2]
            vals = [65, 67, 66, 68]

        return vals.index(ord(c))

    def kbhit(self) -> bool:
        """Returns True if keyboard character was hit, False otherwise."""
        if sys.platform == "win32":
            return msvcrt.kbhit()

        else:
            dr, dw, de = select([sys.stdin], [], [], 0)
            return dr != []


class Listener:
    """A class that listens for keyboard input and calls a given function."""

    def __init__(self, on_press: Callable[[str], bool]) -> None:
        """
        Creates a listener that calls the given function on keyboard input.

        Args:
            on_press: A function that takes a single character and returns
                True to continue listening.
        """
        self._thread = self._build_listener(on_press)
        self._stop = False
        self._keyboard = _KBHit()

    @property
    def is_listening(self) -> bool:
        """Returns True if the listener is listening for keyboard input."""
        return self._thread.is_alive()

    def start(self) -> None:
        """Starts the listener."""
        self._thread.start()

    def stop(self) -> None:
        """Stops the listener."""
        self._stop = True
        self._thread.join()
        self._keyboard.set_normal_term()

    def _build_listener(self, on_press: Callable[[str], bool]) -> threading.Thread:
        """Builds a thread that listens for keyboard input and calls the given."""

        def listen() -> None:
            """Listens for keyboard input and calls the given function."""
            while not self._stop:
                if self._keyboard.kbhit():
                    c = self._keyboard.getch()
                    if not on_press(c):
                        break
            self._keyboard.set_normal_term()

        return threading.Thread(target=listen)


if __name__ == "__main__":

    def on_press(c: str) -> bool:
        print(c)
        if c == "q":
            return False
        return True

    keyboard_listener = Listener(on_press)

    keyboard_listener.start()
    print("Listening...")
    print("Press q to quit")

    while keyboard_listener.is_listening:
        pass

    keyboard_listener.stop()
    print("Done")
