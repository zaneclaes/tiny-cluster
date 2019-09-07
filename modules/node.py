#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.kiosk import *
from modules.monitor import *
from modules.kubernetes import *

"""
Manage a Node (each instance of this class controls a single device)
"""
class Node():
  fp_autostart = '~/.config/lxsession/LXDE-pi/autostart'
  bluetooth_config = None

  def __init__(self, hc, node_name, node_cfg):
    self.hc = hc
    self.name = node_name
    self.cfg = node_cfg
    self.log = logging.getLogger(self.name)
    self.dir_backup = f'{self.hc.cwd}/raspberry-pi/backup/{self.name}'

    self.username = 'pi'
    self.user_address = f'{self.cfg["username"]}@{self.cfg["ip"]}'
    self.hostname = self.cfg["hostname"] if self.cfg["hostname"] else self.name

    self.kiosk = Kiosk(self, self._get_merged_config('kiosk'))
    self.monitor = Monitor(self, self._get_merged_config('monitor'))

    self.log.debug(f'loaded node for {self.user_address}')

  # Merge the default config & this node config (or return None if not configured for this node)
  def _get_merged_config(self, key):
    if self.cfg[key] == False or self.cfg[key] == None:
      self.log.debug(f'{key} disabled')
      return None
    cfg = dict(self.hc.cfg[key])
    if type(self.cfg[key]) == dict or type(self.cfg[key]) == list:
      cfg = always_merger.merge(cfg, self.cfg[key])
    return cfg

  # Execute a shell command on the local machine.
  def _sh(self, cmd):
    return self.hc._proc(f'{cmd} {self.hc.stdout}')

  # Execute a single shell command on the kiosk.
  def _ssh(self, cmd, suffix = ''):
    cmd = cmd.replace('"', '\\"')
    return self.hc._proc(f'ssh "{self.user_address}" "{cmd}" {suffix}')

  def _apt(self, cmd, values = ''):
    if cmd != 'autoremove': cmd = f'apt-get {cmd}'
    else: cmd = f'apt {cmd}'
    self._ssh(f'sudo {cmd} {self.hc.apt_flags} {values}')

  # Upload a file from the local machine [raspberry-pi] to the kiosk.
  def _upload(self, fp_remote, fp_local = None):
    if not fp_local: fp_local = self._get_local_fp(fp_remote)
    return self.hc._proc(f'scp {self.hc.q} "{fp_local}" "{self.user_address}:{fp_remote}"')

  # Download a file from the kiosk to the local machine.
  def _download(self, fp_remote, fp_local = None):
    if not fp_local: fp_local = self._get_local_fp(fp_remote)
    self._sh(f'mkdir -p {os.path.dirname(fp_local)}')
    self.log.debug(f'{fp_remote} -> {fp_local}')
    return self.hc._proc(f'scp {self.hc.q} "{self.user_address}:{fp_remote}" "{fp_local}"')

  # download a file from this node to a dedicated rapberry-pi/backup folder
  def _backup(self, fp_remote):
    self._download(fp_remote, f'{self.dir_backup}/{fp_remote}')

  # upload a backed-up file to this node
  def _restore(self, fp_remote):
    self._upload(f'{self.dir_backup}/{fp_remote}', fp_remote)

  # Get the path at which to store a local file.
  def _get_local_fp(self, fp_remote):
    if fp_remote.startswith('.'): fp_remote = fp_remote[1:]
    return f'{self.hc.cwd}/raspberry-pi/{fp_remote}'

  def _get_bt_mac_addr(self):
    if bluetooth_config: return self.bluetooth_config
    self.bluetooth_config = self._ssh('hcitool dev | grep -o "[[:xdigit:]:]\\\{11,17\\\}"')
    return self.bluetooth_config

  # Add a bash line to the autostart file
  def _autostart(self, bash):
    self.log.info(f'adding startup command `{bash}`...')
    bash = bash.replace('"', '\\"')
    self._ssh(f'echo "@bash {bash}" > {self.fp_autostart}')

  # Write all the configuration values.
  def configure(self):
    self.log.info(f'setting hostname to {self.hostname}...')
    self._ssh(f'sudo hostname {self.hostname}')

    self._ssh(f'mkdir -p {os.path.dirname(self.fp_autostart)}')
    self._ssh(f'rm {self.fp_autostart}', '|| true')

    usb_flag = '1' if self.cfg['usb_ethernet'] else '0'
    usb_buspower = '/sys/devices/platform/soc/3f980000.usb/buspower'
    self._autostart(f'echo "{usb_flag}" | sudo tee {usb_buspower} >/dev/null')

    hdmi_flag = '-p' if self.cfg['hdmi'] else '-o'
    self._autostart(f'tvservice {hdmi_flag}')

    self.kiosk.configure()
    self.monitor.configure()

  # ensure all software is up-to-date
  def update(self):
    self.log.info(f'upating packages...')
    self._apt('update')
    self._apt('upgrade')
    self._apt('dist-upgrade')

    self.log.info(f'cleaning up...')
    self._apt(f'autoremove {self.hc.stdout}')

  # Reboot the node
  def reboot(self):
    self.log.info(f'rebooting...')
    self._ssh('sudo reboot', '|| true')

  # EVERYTHING (setup node from scratch)
  def setup(self):
    # Ensure that this machine can SSH in to the node
    fp = os.path.expanduser('~/.ssh/id_rsa')
    if os.path.isfile(fp):
      self.log.info(f'configuring SSH access for {fp} to {self.user_address}...')
      self._sh(f'ssh-copy-id -i {fp} {self.user_address}')

    self.update()
    self.kiosk.setup()
    self.monitor.setup()

    self.configure()
    self.update()
    self.reboot()

  # Public: execute any shell command on a kiosk. Syntatictic sugar of a name for sshing a cmd.
  def exec(self):
    self.log.info(f'exec {self.hc.args.cmd}')
    self._ssh(self.hc.args.cmd)
