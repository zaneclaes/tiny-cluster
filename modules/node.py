#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.kiosk import *
from modules.instance import *

"""
Manage a Node (each instance of this class controls a single device)
"""
class Node(Instance):
    _fp_autostart = '~/.config/lxsession/LXDE-pi/autostart'
    _bluetooth_mac = None

    def __init__(self, cluster, node_cfg):
        if not 'name' in node_cfg:
            raise Exception(f'node configuration missing name: {node_cfg}')
        if len(node_cfg['name']) < 3:
            raise Exception(f'node name too short: {node_cfg["name"]}')
        super(Node, self).__init__(cluster, node_cfg['name'], node_cfg)
        if not self.connect: raise Exception('nodes must have connect configuration')
        self.orig_cfg = dict(node_cfg)
        # self.dir_backup = f'{self.cluster.cwd}/raspberry-pi/backup/{self.name}'
        self.dir_home = f'/home/{self.cfg["username"]}'
        self.kiosk = Kiosk(self, self._get_merged_config('kiosk'))
        self.log.debug(f'loaded node {self.user_address} [{self.name}.local]')

    # Merge the default config & this node config (or return None if not configured for this node)
    def _get_merged_config(self, key):
        if not key in self.cfg:
            self.log.warning(f'{key} missing in {self.cfg}')
        if self.cfg[key] == False or self.cfg[key] == None:
            self.log.debug(f'{key} disabled')
            return None
        cfg = dict(self.cluster.defaults[key])
        if type(self.cfg[key]) == dict or type(self.cfg[key]) == list:
            cfg = always_merger.merge(cfg, self.cfg[key])
        return cfg

    # # download a file from this node to a dedicated rapberry-pi/backup folder
    # def _backup(self, fp_remote):
    #     self._download(fp_remote, f'{self.dir_backup}/{fp_remote}')

    # # upload a backed-up file to this node
    # def _restore(self, fp_remote):
    #     self._upload(f'{self.dir_backup}/{fp_remote}', fp_remote)

    # Get the path at which to store a local file.
    def _upload_rp_file(self, fp_remote):
        fp_local = fp_remote
        if fp_local.startswith('.'): fp_local = fp_local[1:]
        fp_local = f'{self.cluster.cwd}/raspberry-pi/{fp_local}'
        return self._upload(fp_local, fp_remote)

    # Return the MAC addr of the bluetooth, if available
    def _get_bt_mac_addr(self):
        if not self._bluetooth_mac:
            cmd = 'hcitool dev | grep -o "[[:xdigit:]:]\\\{11,17\\\}"'
            self._bluetooth_mac = self.exec(cmd, capture_output=True).stdout
        return self._bluetooth_mac

    # Add a bash line to the autostart file
    def _autostart(self, bash):
        self.log.info(f'adding startup command `{bash}`...')
        bash = bash.replace('\'', '\\\'')
        self.exec(f'echo \'{bash}\' >> autostart.sh')

    # Write all the configuration values.
    def configure(self):
        self.log.info('configuring...')
        self._upload_rp_file('autostart.sh')
        self._upload_rp_file('startup.sh')
        self.exec('chmod +x autostart.sh')

        startup_flags = []
        if not self.cfg['usb_ethernet']: startup_flags.append('--no-usb_ethernet')
        if not self.cfg['hdmi']: startup_flags.append('--no-hdmi')
        startup_flags = " ".join(startup_flags)

        self.exec(f'mkdir -p {os.path.dirname(self._fp_autostart)}')
        self.exec(f'echo "@bash /home/pi/startup.sh {startup_flags}" > {self._fp_autostart}')

        self.kiosk.configure()
        self.join()

    # Set hostname & IP
    def _setup_network(self):
        self.log.info('setting up network interface...')
        self._upload_rp_file('setup-network.sh')
        args = f'"{self.name}" "{self.cfg["address"]}" "{self.cfg["dns"]}" "{self.cfg["interface"]}"'
        self.exec(f'bash ./setup-network.sh {args}')

    # Install docker & kubeadm
    def _setup_kubeadm(self):
        self.log.info('installing kubeadm, this may take a while...')
        self._upload_rp_file('setup-kubeadm.sh')
        self.exec(f'bash ./setup-kubeadm.sh')

    # EVERYTHING (setup node from scratch)
    def setup(self):
        self.ssh_copy_id()
        self.update()

        self._setup_network()
        self._setup_kubeadm()
        self.kiosk.setup()

        self.configure()
        self.update()
        self.reboot()

    # (Re)join the Kubernetes cluster, applying labels in the process.
    def join(self):
        if not self.cluster.master:
            self.log.error('Nothing to join: there is no master Kubernetes node.')
            return
        self.log.info('leaving cluster...')
        self.exec('sudo kubeadm reset -f || true')

        self.log.info('joining cluster...')
        cmd = self.cluster.master._get_join_command()
        if len(cmd) <= 0: raise Exception('failed to retrieve kubeadm join command')
        self.exec(f'sudo {cmd}')

        for label in self.cfg['labels']:
            self.log.info(f'applying label "{label}"...')
            self.cluster.master.exec(f'kubectl label nodes {self.name} {label} --overwrite')
