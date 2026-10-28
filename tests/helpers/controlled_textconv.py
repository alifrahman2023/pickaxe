"""Identity text conversion with socket-controlled cancellation points (#18)."""

import json
import os
from pathlib import Path
import signal
import socket
import sys


socket_path, phase, blob_path = sys.argv[1:]
content = Path(blob_path).read_bytes()
blocker = b"needle newest" if phase == "before" else b"needle x index"

if blocker in content:
    with socket.socket(socket.AF_UNIX) as connection:
        connection.connect(socket_path)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        connection.sendall((json.dumps({
            "event": "ready", "pid": os.getpid(),
            "parent": os.getppid(), "group": os.getpgrp(),
        }) + "\n").encode("ascii"))
        connection.recv(1)

sys.stdout.buffer.write(content)
