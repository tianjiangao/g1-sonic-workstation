"""Build new models from audited assets; never execute the downloaded builder."""
import argparse,copy,hashlib,json
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent

def _inertial(body,link):
    src=link.find('inertial');origin=src.find('origin');tensor=src.find('inertia')
    if origin.get('rpy','0 0 0')!='0 0 0':raise ValueError('Unsupported inertial frame')
    for old in body.findall('inertial'):body.remove(old)
    body.insert(0,ET.Element('inertial',pos=origin.get('xyz'),mass=src.find('mass').get('value'),fullinertia=' '.join(tensor.get(k) for k in ('ixx','iyy','izz','ixy','ixz','iyz'))))

def build(output):
    output=Path(output)
    if output.exists():raise FileExistsError('Choose a NEW model output directory; never overwrite existing assets')
    vendor=HERE/'vendor/dex1_reference';manifest=json.loads((vendor/'download-manifest.json').read_text())
    for name,info in manifest['files'].items():
        if hashlib.sha256((vendor/name).read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Reference asset changed: '+name)
    source=ROOT/'gear_sonic_deploy/g1/g1_29dof.xml';xml=ET.parse(source).getroot()
    urdf=ET.parse(vendor/'assets/g1_29dof_with_dex1_1.urdf').getroot();reference=ET.parse(vendor/'assets/g1_29dof_with_grippers.xml').getroot()
    meshroot=ROOT/'gear_sonic/data/robot_model/model_data/g1/meshes';asset=xml.find('asset')
    xml.find('compiler').set('meshdir','.')
    for mesh in list(asset):
        if 'rubber_hand' in mesh.get('name',''):asset.remove(mesh)
        elif mesh.tag=='mesh':mesh.set('file',str(meshroot/mesh.get('file')))
    for mesh in reference.findall('./asset/mesh'):
        if 'dex1_1/' in mesh.get('file',''):
            copied=copy.deepcopy(mesh);copied.set('file',str(vendor/'assets'/mesh.get('file')));asset.append(copied)
    mounts={};limits={}
    for side in ('left','right'):
        wrist=xml.find(f'.//body[@name="{side}_wrist_yaw_link"]')
        _inertial(wrist,urdf.find(f'link[@name="{side}_wrist_yaw_link"]'))
        for child in list(wrist):
            if child.tag=='geom' and ('rubber_hand' in child.get('mesh','') or 'hand_palm' in child.get('mesh','')):wrist.remove(child)
        mount=urdf.find(f'joint[@name="{side}_base_joint"]/origin')
        if mount.get('rpy','0 0 0')!='0 0 0':raise ValueError('Unexpected wrist mount rotation')
        base=copy.deepcopy(reference.find(f'.//body[@name="{side}_dex1_base_link"]'));base.set('pos',mount.get('xyz'));wrist.append(base);mounts[side]=dict(mount.attrib)
        for finger in (1,2):
            name=f'{side}_dex1_finger_joint_{finger}';j=urdf.find(f'joint[@name="{name}"]');limit=j.find('limit')
            if j.get('type')!='prismatic' or j.find('origin').get('rpy','0 0 0')!='0 0 0':raise ValueError('Unexpected finger joint')
            mj=base.find(f'.//joint[@name="{name}"]');mj.set('range',limit.get('lower')+' '+limit.get('upper'));mj.set('axis',j.find('axis').get('xyz'));limits[name]=dict(limit.attrib)
            motor=copy.deepcopy(reference.find(f'./actuator/motor[@joint="{name}"]'));xml.find('actuator').append(motor)
    # Floor/light for a self-contained scene; no controller, service or transport.
    world=xml.find('worldbody')
    for section in xml.findall('worldbody'):
        for geom in list(section.findall('geom')):
            if geom.get('type')=='plane':section.remove(geom)
    ET.SubElement(world,'geom',name='offline_floor',type='plane',size='0 0 .05',rgba='.86 .89 .91 1')
    ET.SubElement(world,'light',pos='1 -2 3',dir='-1 2 -3',diffuse='.8 .8 .8')
    xml.set('model','g1_sonic_dex1');output.mkdir(parents=True)
    def save(root,name):ET.indent(root);ET.ElementTree(root).write(output/name,encoding='utf-8',xml_declaration=True)
    save(xml,'g1_sonic_dex1.xml')
    passive=copy.deepcopy(xml)
    for node in list(passive):
        if node.tag=='actuator':passive.remove(node)
    save(passive,'g1_sonic_dex1_passive.xml')
    report={'source_body':str(source),'reference_revision':manifest['revision'],'body_motors':29,'visual_finger_dofs':4,'actuated_model_nu':33,'passive_model_nu':0,'mounts':mounts,'urdf_limits':limits,'closure_trim_applied':False,'license_note':'Hub model-card license unspecified; supplied HIW500 reference LICENSE is Apache-2.0; retain provenance and review before redistribution.','downloaded_builder_executed':False}
    report['mesh_sha256']={m.get('file'):hashlib.sha256(Path(m.get('file')).read_bytes()).hexdigest() for m in xml.findall('./asset/mesh')}
    report['hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.glob('*.xml')}
    (output/'build-report.json').write_text(json.dumps(report,indent=2));return report
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default=str(HERE/'assets_dex1_v3'));a=p.parse_args();print(json.dumps(build(a.output),indent=2))
