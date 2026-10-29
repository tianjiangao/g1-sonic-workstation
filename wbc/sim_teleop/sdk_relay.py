"""Only bridge fixed localhost PC Service SDK port; never import DDS/robot SDK."""
import argparse
import os
from pathlib import Path
import selectors
import socket
import threading


def copy_pair(a, b):
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(a, selectors.EVENT_READ, b)
            sel.register(b, selectors.EVENT_READ, a)
            while True:
                for key, _ in sel.select(timeout=1):
                    data = key.fileobj.recv(65536)
                    if not data: return
                    key.data.sendall(data)
    except (OSError, TimeoutError):
        pass
    finally:
        a.close(); b.close()


def serve(path, inside):
    if inside:
        from sim_teleop.safety import assert_isolated
        assert_isolated()
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1',60061))
    else:
        # Parent directory is private to the user and unique per run.
        if Path(path).exists(): raise RuntimeError('Refusing existing Unix socket')
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(path)
        os.chmod(path, 0o600)
    listener.listen(4)
    print('SDK_RELAY_READY', 'inside' if inside else 'host:127.0.0.1:60061', flush=True)
    while True:
        a, _ = listener.accept()
        try:
            if inside:
                b = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); b.connect(path)
            else:
                b = socket.create_connection(('127.0.0.1',60061), timeout=2)
                b.settimeout(None)
            threading.Thread(target=copy_pair, args=(a,b), daemon=True).start()
        except OSError as e:
            print('SDK_RELAY_ERROR',str(e),flush=True); a.close()

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('path');p.add_argument('--inside',action='store_true')
    a=p.parse_args();serve(a.path,a.inside)
