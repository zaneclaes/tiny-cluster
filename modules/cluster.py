#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from modules.node import *
from deepmerge import always_merger, conservative_merger

"""
Manage a cluster of nodes
"""
class Cluster():
    nodes = {} # Node objects keyed by IP address.
    node_name_to_ip = {} # Reverse lookup name of a node to its IP address.

    # https://raspberrypi.stackexchange.com/questions/28365/what-are-the-possible-ouis-for-the-ethernet-mac-address
    pi_ouis = ['b8:27:eb', 'dc:a6:32']

    def __init__(self, nodes, defaults):
        # Create the node instances and run the method.
        self.defaults = dict(defaults)
        self.nodes = {}
        self.master = None

        # Load Kubernetes settings.
        if defaults['kubernetes']:
            self.network = defaults['kubernetes']['network']
            if not self.network: self.network = {}
            self.context = defaults['kubernetes']['context']
            self.cluster = defaults['kubernetes']['cluster']
            self.protected = defaults['kubernetes']['protected']
            if not self.context or not self.cluster:
                raise Exception(f'Missing context/cluster')
            self.log = logging.getLogger(self.cluster)
        else:
            self.log = logging.getLogger('cluster')

        for node_ip in nodes:
            self.create_node(node_ip, nodes[node_ip])

    # Get a node by name, and run a method by name on it.
    def node_exec(self, node_name, method):
        if not node_name in self.node_name_to_ip:
            raise Exception(f'No node named {node_name}')
        self.instance = self.nodes[self.node_name_to_ip[node_name]]

        # Call the work function.
        self.log.debug(f'run {self}')
        if not hasattr(self.instance, method):
            raise Exception(f'{method} is not valid on {node_name}.')
        getattr(self.instance, method)()

    # Create a new device.
    def create(self):
        self.log.info('setting up...')
        ip_address = input('''Enter the IP address of the device.
Leave blank to scan the network (auto-detect): ''')
        if not ip_address:
            ip_addresses = self.scan_network(self.pi_ouis)
            if len(ip_addresses) <= 0:
                self.log.error('''No Raspberry Pis could be automatically detected.
You could run `arp -d -a` to flush the cache, or `arp -a` to ensure that the device appears.''')
                return
            ip_address = self.list_menu_input(ip_addresses, 'Select an IP address: ')

        # Set up node?
        n = input(f'What is the name for the node at {ip_address}? ')
        if len(n) < 2:
            print(f'The name was too short. Aborted setup.')
            exit(0)

        update_cfg = {'name': n}

        if ip_address in self.nodes:
            node = self.nodes[ip_address]
            self.log.info(f'using existing node "{node.name}" for {ip_address}')
        else:
            # Make it master?
            if not self.master:
                is_mstr = input(f'''Should this be the master? [Y/n]: ''')
                if is_mstr.lower() != 'n':
                    update_cfg['master'] = True
            node = self.create_node(ip_address, update_cfg)
            self.log.info(f'creating node "{node.name}" for {ip_address}')
            node._ssh_copy_id()

        if not update_cfg['network']: update_cfg['network'] = {}
        update_cfg['network']['interface'] = node._get_best_interface(ip_address)
        self.update_node_cfg(ip_address, update_cfg)
        self.nodes[ip_address].create()

    # Instantiate a node.
    def create_node(self, node_ip, cfg):
        cfg = dict(cfg)
        cfg['address'] = node_ip
        cfg = conservative_merger.merge(cfg, self.defaults['node'])
        node = Node(self, cfg)
        if node.name in self.node_name_to_ip:
            raise Exception(f'''the node name {node.name} is being claimed for {node_ip}.
It previously appeared for {self.node_name_to_ip[node_ip]}')''')
        self.node_name_to_ip[node.name] = node_ip
        self.nodes[node_ip] = node

        if node.master:
            if self.master:
                raise Exception(f'A master was already defined, so {node_ip} cannot become it.')
            self.master = node.master
        return node

    # Update config.yaml with a node's config (non-destructive).
    def update_node_cfg(self, ip_address, update_cfg):
        self.log.info(f'writing out configuration for {ip_address}')
        cust = {}
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream: cust = yaml.safe_load(stream)
        if not 'nodes' in cust: cust['nodes'] = {}
        if not ip_address in cust['nodes']: cust['nodes'][ip_address] = {}
        keys = list(update_cfg)
        def_node = dict(self.defaults['node'])
        for key in keys:
            if key in def_node and def_node[key] == update_cfg[key]:
                self.log.debug(f'{key} matches node default value of {update_cfg[key]}')
                del update_cfg[key]
        vals = always_merger.merge(cust['nodes'][ip_address], update_cfg)
        if 'address' in vals: del vals['address']
        cust['nodes'][ip_address] = vals
        with open(self.fp_cfg, 'w') as file:
            yaml.dump(cust, file, default_flow_style=False)

    # Inspired by: https://github.com/TranceCat/Raspberry-Pi-orchestration
    def scan_network(self, ouis):
        self.log.info('scannning network...')
        ip_addresses = set()
        addr_matcher = re.compile('\((?P<ip>[0-9\.]*)\)\s*(?P<mac>[0-9a-z:]*)')
        p = subprocess.Popen("arp -a | cut -f 2,4 -d ' ' ", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
            line = line.decode('utf-8').strip()
            self.log.debug(f'found device on network: {line}')
            match = addr_matcher.match(line)
            if not match or not match.group('mac'): continue
            mac = match.group('mac')
            oui_matches = [o for o in ouis if mac.startswith(o)]
            if len(oui_matches) > 0: ip_addresses.add(match.group('ip'))
        ip_addresses = list(ip_addresses)
        ip_addresses.sort()
        return ip_addresses

    def list_menu_input(self, arr, prompt = ''):
        i = 0
        while i < len(arr):
            i += 1
            print(f'{i}) {arr[i-1]}')
        i = int(input(prompt))
        return arr[i-1]