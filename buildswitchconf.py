#!/usr/bin/env python3

import yaml
import re
from jinja2 import Template

file = "switchports.yaml"


def convert_range_to_ports(s):
    # Find prefix
    prefix_match = re.match('^(?P<prefix>[A-Za-z_/\d]*[A-Za-z_/]+)(?P<range>[\d\-,]+)$', s)
    if not prefix_match:
        raise Exception(f"{s} does not appear to be a valid interface name or range")

    prefix = prefix_match.group('prefix')
    port_range = prefix_match.group('range')
    port_lists = port_range.split(',')

    range_regex = re.compile('^(?P<start>\d+)-(?P<end>\d+)$')

    ports = []
    for port in port_lists:
        if '-' in port:
            matches = range_regex.match(port)
            if not matches:
                raise Exception(f"{s} does not appear to be a valid interface name or range")

            m = matches.groupdict()
            for i in range(int(m['start']), int(m['end'])+1):
                ports.append(prefix+str(i))
        else:
            ports.append(prefix+port)
    return ports

# Load config
with open(file) as conf_file:
    config = yaml.load(conf_file)

# Load templates for each switch type
switchbrands = set()
for switch, switch_info in config['switches'].items():
    switchbrands.add(switch_info['type'])

templates = {}
for brand in switchbrands:
    with open(brand + '.j2') as template:
        templates[brand] = Template(template.read())

# Set up switch data structure
switches = { switch: { 'vlans': set(), 'ports': {}} for switch in config['switches'].keys() }
for switch, definition in config['switches'].items():
    for port_type, count in definition['ports'].items():
        if count == 0:
            switches[switch]['ports'][port_type+'0'] = { 'vlans': set(), 'description': None }
        else:
            for i in range(1, int(count)+1):
                switches[switch]['ports'][port_type+str(i)] = { 'vlans': set(), 'description': None }

# Flatten out infra_groups
vlan_groups = {}
for infra, vlans in config['vlan_groups'].items():
    for vlan, vlan_def in vlans.items():
        vlan_groups['_'.join([infra, vlan])] = vlan_def

# Assign VLANs to ports
for vlan_group, vlan_def in vlan_groups.items():
    vlans = vlan_def['vlans']
    for switch, port_defs in vlan_def['ports'].items():
        ports = convert_range_to_ports(port_defs)
        for port in ports:
            if switches[switch]['ports'][port]['description']:
                raise Exception(f"{port} on {switch} defined twice ({switches[switch]['ports'][port]['description']} and {vlan_group})")
            switches[switch]['ports'][port]['vlans'] = vlans
            switches[switch]['ports'][port]['description'] = vlan_group

# For each port, determine trunk or access, and make sure each switch is configured for all its vlans
for switch, switchinfo in switches.items():
    switch_vlans = set()
    for portname, portinfo in switchinfo['ports'].items():
        if len(portinfo['vlans']) > 1:
            portinfo['mode'] = 'trunk'
        elif len(portinfo['vlans']) == 1:
            if '-' in str(portinfo['vlans'][0]):
                portinfo['mode'] = 'trunk'
            elif portinfo['vlans'][0] != 1:
                portinfo['mode'] = 'access'
        for vlan in portinfo['vlans']:
            if vlan in config['vlans']:
                switch_vlans.add(vlan)
    switchinfo['vlans'] = { vlan: config['vlans'][vlan] for vlan in switch_vlans }


for switch, switchinfo in switches.items():
    with open(switch + '_config', 'w') as switch_config_file:
        switchconfig = templates[config['switches'][switch]['type']].render(switchinfo)
        switch_config_file.write(switchconfig)

# For debugging purposes
print(templates['arista'].render(switches['sw-xe-1']))
