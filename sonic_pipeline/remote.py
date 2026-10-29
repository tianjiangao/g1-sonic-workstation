"""Approved two-hop transport: authenticate the second SSH on the jump host.

Uses the workstation's live control socket for hop1 and jump-host existing keys
for hop2. Never reads, copies, prints or stores private keys/passwords.
"""
import shlex,subprocess
from sonic_pipeline.settings import HOME
JUMP_SOCKET='/opt/g1/user/.cache/sonic-cloud/jump.sock'
REMOTE_ROOT='/srv/g1/sonic-vla'

def command(remote_argv):
 nested=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=8','-p','22','unitree@192.0.2.20']+[shlex.join(remote_argv)]
 return ['ssh','-T','-S',JUMP_SOCKET,'-o','BatchMode=yes','-p','22','jump-user@192.0.2.10',shlex.join(nested)]

def run(remote_argv,input=None,**kwargs):return subprocess.run(command(remote_argv),input=input,check=True,**kwargs)
