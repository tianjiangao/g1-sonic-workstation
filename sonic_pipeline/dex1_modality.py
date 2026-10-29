"""Official GR00T NEW_EMBODIMENT extension: SONIC64 + two real Dex1 angles.

This is deliberately not the stock 78D UNITREE_G1_SONIC/Dex3 embodiment.
"""
from gr00t.configs.data.embodiment_configs import register_modality_config
from gr00t.data.embodiment_tags import EmbodimentTag
from gr00t.data.types import ModalityConfig,ActionConfig,ActionRepresentation,ActionType,ActionFormat
CONFIG={
 'video':ModalityConfig(delta_indices=[0],modality_keys=['ego_view','left_wrist','right_wrist']),
 'state':ModalityConfig(delta_indices=[0],modality_keys=['body','left_gripper','right_gripper','projected_gravity']),
 'action':ModalityConfig(delta_indices=list(range(40)),modality_keys=['motion_token','left_gripper','right_gripper'],action_configs=[ActionConfig(rep=ActionRepresentation.ABSOLUTE,type=ActionType.NON_EEF,format=ActionFormat.DEFAULT) for _ in range(3)]),
 'language':ModalityConfig(delta_indices=[0],modality_keys=['annotation.human.task_description']),
}
register_modality_config(CONFIG,embodiment_tag=EmbodimentTag.NEW_EMBODIMENT)
