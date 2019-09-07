#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.node import *

"""
Manage Home Assistant (singleton)
"""
class HomeAssistant():
  def __init__(self, ha_cfg):
    self.cfg = ha_cfg
    self.url = f"{self.cfg['schema']}://{self.cfg['ip']}:{self.cfg['port']}"
    self.log = logging.getLogger('home-assistant')
    self.log.debug(f'loaded home-assistant [{self.url}]')

  def tab_url(self, tab, kiosk = True, show_tabs = False):
    qp = []
    if kiosk: qp.append('kiosk')
    if show_tabs: qp.append('show_tabs')
    return f'{self.url}/lovelace/{tab}?{"&".join(qp)}'

"""
MAIN
"""
if __name__ == "__main__":
  try:                fp_self = os.readlink(__file__)
  except OSError:     fp_self = __file__
  cwd = os.path.dirname(fp_self)
  fp_def = f'{cwd}/defaults.yaml'
  fp_cfg = f'{cwd}/config.yaml'

  if not os.path.isfile(fp_cfg):
    raise Exception(f'Missing {fp_cfg}. Please see setup instructions.')
  with open(fp_def, 'r') as stream: cfg = yaml.safe_load(stream)
  with open(fp_cfg, 'r') as stream: cfg = always_merger.merge(cfg, yaml.safe_load(stream))

  script = os.path.basename(__file__)
  log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
  methods = [c for c in dir(Node) if not c.startswith('_')]

  # Get the first two positional arguments (node, method)
  parser = argparse.ArgumentParser()
  parser.add_argument('node', choices=list(cfg['nodes']), help='node to interact with')
  parser.add_argument('method', choices=methods, help='what to do with the node')
  opts = parser.parse_args(sys.argv[1:3])

  parser = argparse.ArgumentParser(f'{script} {opts.node} {opts.method}')
  if (opts.method == 'exec'):
    parser.add_argument('cmd', help='a command to run via SSH on this node')
  parser.add_argument('--log-level', '-l', choices=log_levels, default='INFO', help='logging level')
  args = parser.parse_args(sys.argv[3:])
  logging.basicConfig(format='[%(levelname)s] [%(name)s] %(message)s', level=args.log_level)

  # Create the kiosk instances and run the method.
  ha = HomeAssistant(cfg['homeassistant'])

  nodes = {}
  for node_name in cfg['nodes']:
    node_cfg = dict(cfg['node'])
    node_cfg.update(cfg['nodes'][node_name])
    nodes[node_name] = Node(node_name, node_cfg)
  getattr(kiosks[opts.node], opts.method)()
