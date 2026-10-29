"""Camera-only login service guard; stdlib-only so the same file runs on Orin."""
import hashlib
import os
from pathlib import Path
import socket
import sys

BASE = Path('/home/unitree/sonic_official_camera_7f151314')
SERVICE = 'sonic-three-camera.service'
# Existing reviewed deployment, including its physical left/right mapping.
HASHES = {
    'start_three.sh': '6a41f8a9f70ee33b4fe2c38847f890e1ddb7baf9d15b7ffa58c45b8868977bbf',
    'gear_sonic/camera/composed_camera.py': '0d86a739511ea016e25f1d8b54840efd2b8bbf9d121f749450c8437e3bf3b405',
    'gear_sonic/camera/drivers/usb_camera.py': '9b7fb20af155f47924a75edcce858e54d21824670883990477aba1f9bf0950a8',
    'gear_sonic/camera/drivers/realsense.py': '1f80954faa863c88bf0f1c8982c7b2f4499a73881caa618534578255fa63fd87',
    'gear_sonic/camera/sensor_server.py': 'cadaf157e02220b0f6a75f5daf95be207160fc013d560909492c1f49769331c1',
}


def verify_sources(base=BASE, hashes=HASHES):
    for name, digest in hashes.items():
        if hashlib.sha256((base / name).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Reviewed camera source changed: ' + name)


def verify_idle(proc=Path('/proc'), port=5555):
    for entry in proc.glob('[0-9]*'):
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError):
            continue
        if b'gear_sonic.camera.composed_camera' in args:
            raise RuntimeError('Camera already running, refusing duplicate: ' + entry.name)
    with socket.socket() as probe:
        probe.settimeout(.3)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError('Camera port occupied; refusing replacement')


def preview_note(info, now, fps=0):
    if not info:
        return '等待图像 · SSH自动连接中；可先离线管理片段'
    age = now - info['received_at']
    if age < 0:
        return '预览时间异常 · 等待新画面'
    if age >= 1:
        return f'相机断流 · {age:.1f}秒未更新 · 检查网络/相机服务'
    return f"实时 · {fps:.1f}Hz · {info['shape'][1]}×{info['shape'][0]} · {age:.1f}秒前"


def main():
    try:
        verify_sources()
        verify_idle()
    except (OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr, flush=True)
        return 78  # Permanent guard failure: never auto-restart past this gate.
    os.chdir(BASE)
    os.execv('/bin/bash', ['bash', str(BASE / 'start_three.sh')])


if __name__ == '__main__':
    sys.exit(main())
