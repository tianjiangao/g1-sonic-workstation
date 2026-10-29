"""Passive inventory summaries. Enumeration is never motion acceptance."""
def validate_roles(roles,serials):
    values=[roles.get(k) for k in ('ego_view','left_wrist','right_wrist')]
    return all(values) and len(set(values))==3 and set(values).issubset(serials)

def summarize(inventory):
    devices=inventory.get('camera_devices',[]);controllers=inventory.get('controllers',[])
    service=inventory.get('unitree_sonic',{});blockers=[]
    serials=[d.get('serial') for d in devices]
    if not validate_roles(inventory.get('camera_roles',{}),serials):blockers.append('相机角色未确认')
    if not inventory.get('dex1_units'):blockers.append('Dex1 服务未确认')
    if controllers:blockers.append('已有控制器运行')
    blockers.extend(['Dex1 与 SONIC 控制/采集接口未验收','PICO 真机链路未验收'])
    return {'camera_devices':len(devices),'camera_status':inventory.get('camera_error') or f'识别到 {len(devices)} 台；取帧未在此检查',
            'controller_count':len(controllers),'autostart':service.get('ActiveState','未知')+' / '+service.get('UnitFileState','未知'),
            'ready_for_real_control':False,'blockers':blockers}
