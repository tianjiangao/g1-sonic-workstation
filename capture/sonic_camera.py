"""NVIDIA ImageMessageSchema adapter; normalize official RGB into standard JPEG."""
import math
import msgpack
import cv2
from gear_sonic.camera.sensor_server import ImageMessageSchema
ROLES={'ego_view':'camera_head','left_wrist':'camera_left','right_wrist':'camera_right'}
def packets(raw):
    data=msgpack.unpackb(raw,raw=False)
    images=data.get('images',{});times=data.get('timestamps',{})
    for role,key in ROLES.items():
        if role not in images:continue
        stamp=times.get(role)
        if not isinstance(stamp,(int,float)) or not math.isfinite(stamp):raise ValueError('invalid camera timestamp')
        # Use upstream decoding for legacy base64 RGB and on-device JPEG bytes.
        # Directly saving legacy wire JPEG would swap red/blue on export.
        try:image=ImageMessageSchema.deserialize({'images':{role:images[role]},'timestamps':{role:stamp}}).images[role]
        except (TypeError,cv2.error) as e:raise ValueError('invalid SONIC image '+role) from e
        if image is None or getattr(image,'ndim',0)!=3 or image.shape[2]!=3:raise ValueError('invalid SONIC image '+role)
        ok,jpeg=cv2.imencode('.jpg',cv2.cvtColor(image,cv2.COLOR_RGB2BGR),[cv2.IMWRITE_JPEG_QUALITY,80])
        if not ok:raise ValueError('invalid SONIC JPEG '+role)
        yield key,jpeg.tobytes(),stamp
