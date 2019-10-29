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

    def set_context(self, context, force = False):
        fp_cfg = f'{self.cwd}/contexts/{context}.yaml'
        if not os.path.isfile(fp_cfg) and not force: return False
        self.fp_cfg = fp_cfg
        self.context = context
        return True

    def __init__(self):
        try:                self.fp = os.readlink(__file__)
        except OSError:     self.fp = __file__
        self.cwd = os.path.dirname(self.fp)

        # Load defaults.yaml then merge in config.yaml if it exists
        fp_def = f'{self.cwd}/defaults.yaml'
        with open(fp_def, 'r') as stream: cfg = yaml.safe_load(stream)

        args = sys.argv[1:]
        if len(args) > 0 and self.set_context(args[0]): args = args[1:]
        else: self.set_context(cfg['defaults']['context'], True)

        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream:
                cust = yaml.safe_load(stream)
                cfg = always_merger.merge(cfg, cust)

        self.defaults = cfg['defaults']
        script = os.path.basename(__file__)
        log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
        features = ['master', 'node', 'setup']

        if len(args) > 0 and args[0] in features: scope = args[0]
        else: scope = 'setup'
        parser = argparse.ArgumentParser(f'{script} {self.context}')
        parser.add_argument('scope', choices=features, default='setup')
        parser.add_argument('--log-level', '-l', choices=log_levels, default='INFO', help='logging level')
        parser.add_argument('--log-format', '-f', default='[%(levelname)s] [%(name)s] %(message)s')

        if scope == 'master':
            methods = [c for c in dir(Master) if not c.startswith('_')]
            parser.add_argument('method', choices=methods, nargs='?', help='what to do with the master')
        elif scope == 'node':
            methods = [c for c in dir(Node) if not c.startswith('_')]
            node_names = [cfg['cluster']['nodes'][ip]['name'] for ip in cfg['cluster']['nodes']]
            parser.add_argument('node', choices=node_names, help='node to interact with')
            parser.add_argument('method', choices=methods, help='what to do with the node')
        elif scope == 'setup':
            parser.add_argument('--ip-address', '-ip', type=str, help='ip of the node to set up', required=False)
        self.opts = parser.parse_args(args)

        # parser = argparse.ArgumentParser(f'{script} {self.opts.node} {self.opts.method}')
        # if (self.opts.method == 'exec'):
        #     parser.add_argument('cmd', help='a command to run via SSH on this node')

        # self.args = parser.parse_args(sys.argv[3:])
        logging.basicConfig(format=self.opts.log_format, level=self.opts.log_level)
        self.log = logging.getLogger(self.context)

        # "quiet" flags are enabled unless DEBUG log mode.
        self.quiet = self.opts.log_level != 'DEBUG'
        # self.stdout = '' # '> /dev/null 2>&1' if self.quiet else ''

        # Create master node:
        if cfg['cluster']['master']:
            self.master = Master(self, cfg['cluster']['master'])

        # Create the node instances and run the method.
        self.nodes = {}
        for node_ip in cfg['cluster']['nodes']:
            self.create_node(node_ip, cfg['cluster']['nodes'][node_ip])

        # Call the work function.
        logging.debug(f'run {scope} {self.opts}')
        if scope == 'setup':
            self.setup()
        elif scope == 'node':
            node_ip = self.node_name_to_ip[self.opts.node]
            getattr(self.nodes[node_ip], self.opts.method)()
        else:
            getattr(self.master, self.opts.method)()

    # Setup a new device.
    def setup(self):
        logging.info('setting up...')
        ip_address = self.opts.ip_address
        if not ip_address:
            ip_addresses = self.scan_network(self.pi_ouis)
            if len(ip_addresses) <= 0:
                logging.error('''No Raspberry Pis could be automatically detected.
You could run `arp -d -a` to flush the cache, or `arp -a` to ensure that the device appears.
If you know an IP address, try running this script again with the --ip-address flag.''')
                return
            ip_address = self.list_menu_input(ip_addresses, 'Select an IP address: ')

        node_update_cfg = {}
        if ip_address in self.nodes:
            node = self.nodes[ip_address]
            logging.info(f'using existing node "{node.name}" for {ip_address}')
        else:
            name = input(f'Choose a name for the node at {ip_address}: ')
            if name in self.node_name_to_ip:
                raise Exception(f'The node "{name}" was already claimed by "{self.node_name_to_ip[name]}"')
            node_update_cfg['name'] = name
            node = self.create_node(ip_address, node_update_cfg)
            logging.info(f'creating node "{node.name}" for {ip_address}')
            node.ssh_copy_id()

        logging.info('determining the network interface...')
        node_update_cfg['interface'] = node._get_best_interface(ip_address)

        self.update_node_cfg(ip_address, node_update_cfg)
        c = input(f'Setup node "{node.name}" at {ip_address}? [y/N] ')
        if c.lower() != 'y': return
        self.nodes[ip_address].setup()

    # Instantiate a node.
    def create_node(self, node_ip, cfg):
        cfg['address'] = node_ip
        node = Node(self, always_merger.merge(dict(self.defaults['node']), cfg))
        if node.name in self.node_name_to_ip:
            raise Exception(f'''the node name {node.name} is being claimed for {node_ip}.
It previously appeared for {self.node_name_to_ip[node_ip]}')''')
        self.node_name_to_ip[node.name] = node_ip
        self.nodes[node_ip] = node
        return node

    # Update config.yaml with a node's config (non-destructive).
    def update_node_cfg(self, ip_address, node_update_cfg):
        logging.info(f'writing out configuration for {ip_address}')
        cust = {}
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream: cust = yaml.safe_load(stream)
        if not 'cluster' in cust: cust['cluster'] = {}
        if not 'nodes' in cust['cluster']: cust['cluster']['nodes'] = {}
        if not ip_address in cust['cluster']['nodes']: cust['cluster']['nodes'][ip_address] = {}
        keys = list(node_update_cfg)
        for key in keys:
            if key in self.defaults['node'] and self.defaults['node'][key] == node_update_cfg[key]:
                logging.debug(f'{key} matches node default value of {node_update_cfg[key]}')
                del node_update_cfg[key]
        vals = always_merger.merge(cust['cluster']['nodes'][ip_address], node_update_cfg)
        if 'address' in vals: del vals['address']
        cust['cluster']['nodes'][ip_address] = vals
        with open(self.fp_cfg, 'w') as file:
            yaml.dump(cust, file, default_flow_style=False)

    # Inspired by: https://github.com/TranceCat/Raspberry-Pi-orchestration
    def scan_network(self, ouis):
        logging.info('scannning network...')
        ip_addresses = set()
        addr_matcher = re.compile('\((?P<ip>[0-9\.]*)\)\s*(?P<mac>[0-9a-z:]*)')
        p = subprocess.Popen("arp -a | cut -f 2,4 -d ' ' ", shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for line in p.stdout.readlines():
            line = line.decode('utf-8').strip()
            logging.debug(f'found device on network: {line}')
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
