"""Fail closed before any DDS participant or controller is created."""
import json
import os
from pathlib import Path
import subprocess


def validate_network(current, host, interfaces, routes):
    if current == host:
        raise RuntimeError('BLOCKED: host network namespace')
    if set(interfaces) != {'lo'}:
        raise RuntimeError('BLOCKED: namespace must contain only lo')
    if routes.strip():
        raise RuntimeError('BLOCKED: non-loopback route exists')


def assert_isolated():
    current = os.readlink('/proc/self/ns/net')
    host = os.environ.get('SONIC_HOST_NETNS')
    if not host or not host.startswith('net:['):
        raise RuntimeError('BLOCKED: missing host namespace baseline')
    interfaces = [x['ifname'] for x in json.loads(subprocess.check_output(['ip','-j','link']))]
    routes = subprocess.check_output(['ip','route','show','table','main'], text=True)
    routes6 = subprocess.check_output(['ip','-6','route','show','table','main'], text=True)
    # IPv6 loopback route is harmless; reject all other IPv6 routes.
    other6 = '\n'.join(r for r in routes6.splitlines() if not r.startswith('::1 dev lo '))
    validate_network(current, host, interfaces, routes + other6)
    result = subprocess.run(['ip','route','get','192.168.123.164'], capture_output=True, text=True)
    if result.returncode == 0:
        raise RuntimeError('BLOCKED: robot address has a route')
    # No socket inherited from host namespace. Unix sockets are local IPC and allowed.
    sockets = set()
    for proto in ('tcp','tcp6','udp','udp6','raw','raw6'):
        for row in Path('/proc/self/net', proto).read_text().splitlines()[1:]:
            fields = row.split()
            if len(fields) > 9:
                sockets.add(fields[9])
    unix = {r.split()[6] for r in Path('/proc/self/net/unix').read_text().splitlines()[1:]}
    for fd in Path('/proc/self/fd').iterdir():
        try: link = os.readlink(fd)
        except OSError: continue
        if link.startswith('socket:['):
            inode = link[8:-1]
            if inode not in sockets and inode not in unix:
                raise RuntimeError('BLOCKED: inherited socket from another network namespace')
    return {'network_namespace':current,'host_namespace':host,'interfaces':interfaces,
            'ipv4_routes':routes,'ipv6_routes':routes6,'robot_route':result.stderr.strip(),
            'ros_domain_id':os.environ.get('ROS_DOMAIN_ID'),
            'rmw':os.environ.get('RMW_IMPLEMENTATION'),'unitree_domain_id':0}

if __name__ == '__main__':
    print(json.dumps(assert_isolated(), indent=2))
