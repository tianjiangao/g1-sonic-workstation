"""Bounded automatic SSH transport only; never starts robot control services."""
import ipaddress
from pathlib import Path
import subprocess
import time

class SSHConnectionError(RuntimeError):
    def __init__(self,message,retryable=False):
        super().__init__(message);self.retryable=retryable

ROBOT_IP = '192.168.123.164'
IDENTITY = Path.home()/'.local/share/sonic-workstation/ssh/g1_ed25519'


def ssh_args(host):
    ipaddress.IPv4Address(host)
    cache = Path.home()/'.cache/g1-real-teleop'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    control = cache/('control' if host == ROBOT_IP else 'control-'+host)
    args = ['ssh', '-p', '22', '-S', str(control),
            '-o', 'ControlMaster=auto', '-o', 'ControlPersist=30m',
            '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=5', '-o', 'ConnectionAttempts=1',
            '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
            '-o', 'ForwardAgent=no', '-o', 'ClearAllForwardings=yes']
    if host == ROBOT_IP:
        args += ['-i', str(IDENTITY), '-o', 'IdentitiesOnly=yes',
                 '-o', 'PreferredAuthentications=publickey',
                 '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no']
    return args + ['unitree@'+host]


def connect(host,timeout=12):
    try:
        r = subprocess.run(ssh_args(host)+['hostname'], stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise SSHConnectionError('SSH连接超时；请检查机器人电源和网络',True) from e
    if r.returncode:
        detail=r.stderr.strip()[-800:] or str(r.returncode)
        retryable=any(s in detail.lower() for s in ('connection refused','connection timed out','no route to host','network is unreachable','connection reset','connection closed'))
        raise SSHConnectionError('SSH自动连接失败：'+detail,retryable)
    hostname = r.stdout.strip()
    if host == ROBOT_IP and hostname != 'unitree-g1-nx':
        raise RuntimeError('机器人主机身份不符：'+hostname)
    return {'host': host, 'hostname': hostname}

def wait_for_connection(host,timeout=30,pause=time.sleep,clock=time.monotonic):
    """Wait for boot-time transport only. Never retry auth or identity failures."""
    end=clock()+timeout;last=None
    for attempt in range(30):
        if attempt and clock()>=end:break
        try:return connect(host,timeout=min(12,max(.1,end-clock())))
        except SSHConnectionError as error:
            if not error.retryable:raise
            last=error
            if clock()>=end:break
            print(f'等待机器人SSH就绪（本次启动内重试 {attempt+1}/30）……',flush=True)
            pause(min(1.,max(0.,end-clock())))
    raise RuntimeError('SSH就绪超时；未启动身体控制器：'+str(last))
