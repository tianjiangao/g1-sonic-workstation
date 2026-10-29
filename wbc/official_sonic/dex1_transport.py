"""Scoped hardware DDS setup. Never changes SDK files or body-control DDS."""
def initialize(network):
    from unitree_sdk2py.core import channel
    original=channel.ChannelConfigHasInterface
    # Keep discovery multicast, but send endpoint discovery and motor commands
    # to each matched reader's unicast locator. The wired link was observed to
    # lose DDS multicast commands while local readers still counted them.
    channel.ChannelConfigHasInterface=original.replace('<Interfaces>','<AllowMulticast>spdp</AllowMulticast><Interfaces>')
    try:channel.ChannelFactoryInitialize(0,network)
    finally:channel.ChannelConfigHasInterface=original
    return {'domain':0,'network':network,'allow_multicast':'spdp','motor_data':'unicast','sdk_files_modified':False}
