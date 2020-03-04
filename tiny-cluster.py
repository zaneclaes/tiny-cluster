#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.node import *
from modules.master import *

class TinyCluster():
    nodes = {} # Node objects keyed by IP address.
    node_name_to_ip = {} # Reverse lookup name of a node to its IP address.

    # https://raspberrypi.stackexchange.com/questions/28365/what-are-the-possible-ouis-for-the-ethernet-mac-address
    pi_ouis = ['b8:27:eb', 'dc:a6:32']

    def set_context(self, context):
        self.log.debug(f'Setting context to: {context}')
        self.context = context
        self.fp_cfg = f'{self.cwd}/contexts/{context}.yaml'
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream:
                self.config_context = yaml.safe_load(stream)
        else:
            self.config_context = {}
        self.config = always_merger.merge(self.config_defaults, self.config_context)
        return True

    def __init__(self):
        try:                self.fp = os.readlink(__file__)
        except OSError:     self.fp = __file__
        self.cwd = os.path.dirname(self.fp)

        # Load defaults.yaml then merge in config.yaml if it exists
        fp_def = f'{self.cwd}/defaults.yaml'
        with open(fp_def, 'r') as stream: self.config_defaults = yaml.safe_load(stream)

        script = os.path.basename(__file__)
        log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']

        args = sys.argv[1:]

        methods = set()
        methods.update([c for c in dir(Master) if not c.startswith('_')])
        methods.update([c for c in dir(Node) if not c.startswith('_')])

        parser = argparse.ArgumentParser(f'{script}')
        parser.add_argument('--context', '-c', default='home')
        parser.add_argument('--node', '-n', default='master')
        parser.add_argument('method', choices=methods)
        parser.add_argument('--log-level', '-l', choices=log_levels, default='INFO', help='logging level')
        parser.add_argument('--log-format', '-f', default='[%(levelname)s] [%(name)s] %(message)s')
        self.opts = parser.parse_args(args)

        # parser = argparse.ArgumentParser(f'{script} {self.opts.node} {self.opts.method}')
        # if (self.opts.method == 'exec'):
        #     parser.add_argument('cmd', help='a command to run via SSH on this node')

        # self.args = parser.parse_args(sys.argv[3:])
        logging.basicConfig(format=self.opts.log_format, level=self.opts.log_level)
        self.log = logging.getLogger(self.opts.context)

        # "quiet" flags are enabled unless DEBUG log mode.
        self.quiet = self.opts.log_level != 'DEBUG'
        # self.stdout = '' # '> /dev/null 2>&1' if self.quiet else ''

        self.set_context(self.opts.context)

        # Create master node:
        if self.config['kubernetes'] and self.config['kubernetes']['master']:
            self.nfs = self.config['kubernetes']['nfs']
            self.network_add_on = self.config['kubernetes']['network-add-on']
            if self.network_add_on and self.network_add_on != 'flannel':
                raise Exception('The only networking plugin currently supported is Flannel.')
            self.master = Master(self, self.config['kubernetes']['master'])

        # Create the node instances and run the method.
        self.nodes = {}
        for node_ip in self.config['nodes']:
            self.create_node(node_ip, self.config['nodes'][node_ip])

        if self.opts.node == 'master':
            self.instance = self.master
        elif self.opts.node in self.node_name_to_ip:
            self.instance = self.nodes[self.node_name_to_ip[self.opts.node]]
        else:
            self.instance = None

        # Call the work function.
        self.log.debug(f'run {self.opts}')
        if self.opts.method == 'create':
            if self.instance != None:
                self.instance.create()
            else:
                self.create()
        else:
            if not hasattr(self.instance, self.opts.method):
                raise Exception(f'{self.opts.method} is not valid on {self.opts.node}.')
            getattr(self.instance, self.opts.method)()

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

        # Make it master?
        if not self.master or not self.master.connect:
            is_mstr = input(f'''Should {self.opts.node} be the master? [Y/n]: ''')
            if is_mstr.lower() != 'n':
                self.master = Master(self, self.update_master_cfg(ip_address))
                self.master.update()
                self.master.create()

        # Set up node?
        c = input(f'Confirm: create node "{self.opts.node}" at {ip_address}? [Y/n] ')
        if c.lower() == 'n': return

        update_cfg = {'name': self.opts.node}
        if ip_address in self.nodes:
            node = self.nodes[ip_address]
            self.log.info(f'using existing node "{node.name}" for {ip_address}')
        else:
            node = self.create_node(ip_address, update_cfg)
            self.log.info(f'creating node "{node.name}" for {ip_address}')
            node.ssh_copy_id()

        update_cfg['interface'] = node._get_best_interface(ip_address)
        self.update_node_cfg(ip_address, update_cfg)
        self.nodes[ip_address].update()
        self.nodes[ip_address].create()

    # Instantiate a node.
    def create_node(self, node_ip, cfg):
        cfg['address'] = node_ip
        node = Node(self, always_merger.merge(dict(self.config['defaults']['node']), cfg))
        if node.name in self.node_name_to_ip:
            raise Exception(f'''the node name {node.name} is being claimed for {node_ip}.
It previously appeared for {self.node_name_to_ip[node_ip]}')''')
        self.node_name_to_ip[node.name] = node_ip
        self.nodes[node_ip] = node
        return node

    def update_master_cfg(self, ip_address, username = 'pi'):
        ks = {'address': ip_address, 'connect': 'ssh', 'username': username}
        self.log.info(f'writing out configuration for master: {username}@{ip_address}')
        cust = {}
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream: cust = yaml.safe_load(stream)
        if not 'kubernetes' in cust: cust['kubernetes'] = {}
        cust['kubernetes']['master'] = ks
        with open(self.fp_cfg, 'w') as file:
            yaml.dump(cust, file, default_flow_style=False)
        return ks

    # Update config.yaml with a node's config (non-destructive).
    def update_node_cfg(self, ip_address, update_cfg):
        self.log.info(f'writing out configuration for {ip_address}')
        cust = {}
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream: cust = yaml.safe_load(stream)
        if not 'nodes' in cust: cust['nodes'] = {}
        if not ip_address in cust['nodes']: cust['nodes'][ip_address] = {}
        keys = list(update_cfg)
        def_node = self.config['defaults']['node']
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

"""
MAIN
"""
if __name__ == "__main__":
    cluster = TinyCluster()
