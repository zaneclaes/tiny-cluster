#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.node import *

class HomeCluster():
    def __init__(self):
        try:                self.fp = os.readlink(__file__)
        except OSError:     self.fp = __file__
        self.cwd = os.path.dirname(self.fp)
        fp_def = f'{self.cwd}/defaults.yaml'
        fp_cfg = f'{self.cwd}/config.yaml'

        if not os.path.isfile(fp_cfg):
            raise Exception(f'Missing {fp_cfg}. Please see setup instructions.')
        with open(fp_def, 'r') as stream: self.cfg = yaml.safe_load(stream)
        with open(fp_cfg, 'r') as stream:
          cust = yaml.safe_load(stream)
          self.cfg = always_merger.merge(self.cfg, cust)

        script = os.path.basename(__file__)
        log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
        methods = [c for c in dir(Node) if not c.startswith('_')]

        # Get the first two positional arguments (node, method)
        parser = argparse.ArgumentParser()
        parser.add_argument('node', choices=list(self.cfg['nodes']), help='node to interact with')
        parser.add_argument('method', choices=methods, help='what to do with the node')
        self.opts = parser.parse_args(sys.argv[1:3])

        parser = argparse.ArgumentParser(f'{script} {self.opts.node} {self.opts.method}')
        if (self.opts.method == 'exec'):
          parser.add_argument('cmd', help='a command to run via SSH on this node')
        parser.add_argument('--log-level', '-l', choices=log_levels, default='INFO', help='logging level')
        parser.add_argument('--log-format', '-f', default='[%(levelname)s] [%(name)s] %(message)s')
        self.args = parser.parse_args(sys.argv[3:])
        logging.basicConfig(format=self.args.log_format, level=self.args.log_level)

        # "quiet" flags are enabled unless DEBUG log mode.
        self.quiet = self.args.log_level != 'DEBUG'
        self.stdout = '> /dev/null 2>&1' if self.quiet else ''
        self.apt_flags = '-y -qq' if self.quiet else '-y'
        self.q = '-q' if self.quiet else ''

        # Create the node instances and run the method.
        self.nodes = {}
        for node_name in self.cfg['nodes']:
            node_cfg = dict(self.cfg['node'])
            node_cfg = always_merger.merge(node_cfg, self.cfg['nodes'][node_name])
            self.nodes[node_name] = Node(self, node_name, node_cfg)
        getattr(self.nodes[self.opts.node], self.opts.method)()

    # Run a subprocess
    def _proc(self, cmd):
        logging.debug(cmd)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
          raise Exception(f'[CRITICAL] `{cmd}` error: {stderr.decode("utf-8")}')

        return stdout.decode("utf-8").strip()

"""
MAIN
"""
if __name__ == "__main__":
  hc = HomeCluster()
