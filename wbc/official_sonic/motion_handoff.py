"""Bounded official MotionSwitcher handoff. Inspect is the default."""
import argparse
import contextlib
import sys
import json
import time

def checked_mode(client,pause=time.sleep,deadline=None):
    code=None;data=None
    query_deadline=min(time.monotonic()+8,deadline) if deadline is not None else time.monotonic()+8
    for attempt in range(16):
        if time.monotonic()>=query_deadline:break
        code,data=client.CheckMode()
        if code not in (3102,3103):break
        if attempt<15:
            print(f'运控查询通信尚未就绪（{code}），等待发现后重试只读查询 {attempt+2}/16',file=sys.stderr,flush=True)
            pause(min(.5,max(0.,query_deadline-time.monotonic())))
    if code!=0 or not isinstance(data,dict) or not isinstance(data.get('name'),str):
        raise RuntimeError(f'运控模式查询失败 code={code}（8秒内最多16次只读查询）；未释放运控')
    if data['name'] not in ('','ai'):raise RuntimeError('未知运控模式 '+data['name']+'；拒绝自动释放')
    return data

def handoff(client,release=False,pause=time.sleep):
    deadline=time.monotonic()+25
    before=checked_mode(client,pause,deadline);required=bool(before['name'])
    result={'before':before,'release_required':required,'released':False}
    if not release or not required:return result
    reply=client.ReleaseMode()
    # The pinned official Python SDK returns (code, None), not a bare code.
    code=reply[0] if isinstance(reply,tuple) and len(reply)==2 else reply
    if type(code) is not int or code!=0:raise RuntimeError(f'官方ReleaseMode失败 code={code}；未允许SONIC启动')
    for _ in range(6):
        pause(1);after=checked_mode(client,pause,deadline)
        if not after['name']:return dict(result,after=after,released=True)
    raise RuntimeError('释放后仍为ai模式；未允许SONIC启动')

def main():
    p=argparse.ArgumentParser();p.add_argument('--operator-release',action='store_true');a=p.parse_args()
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import MotionSwitcherClient
    ChannelFactoryInitialize(0,'enp4s0');c=MotionSwitcherClient();c.SetTimeout(2);c.Init()
    with contextlib.redirect_stdout(sys.stderr):result=handoff(c,a.operator_release)
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    try:main()
    except RuntimeError as e:print(str(e),file=sys.stderr,flush=True);sys.exit(2)
