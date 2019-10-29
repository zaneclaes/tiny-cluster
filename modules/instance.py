#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess

"""
Manage a single machine/node/instance (abstract base class)
"""
class Instance():
    _network_interfaces = None

    def __init__(self, cluster, instance_name, instance_cfg):
        self.cluster = cluster
        self.name = instance_name
        self.cfg = instance_cfg
        self.log = logging.getLogger(self.name)
        self.connect = None
        self.address = None
        self.user_address = 'localhost'
        if 'connect' in self.cfg and self.cfg['connect']:
            self.connect = self.cfg['connect']
            if self.connect == 'ssh':
                self.username = self.cfg['username']
                self.address = self.cfg['address']
                self.user_address = f'{self.cfg["username"]}@{self.cfg["address"]}'
            elif self.connect:
                raise Exception(f'unknown connection type: {self.connect}')

    def ssh(self):
        return os.system(f'ssh -o "StrictHostKeyChecking=no" "{self.user_address}"')

    # Execute a command on this instance.
    def exec(self, cmd, check=True, capture_output=False):
        capture_output = capture_output or self.cluster.quiet
        self.log.debug(f'exec({cmd}), check={check}, capture_output={capture_output}')
        args = self._get_proc_args(cmd)
        return subprocess.run(args, shell=True, check=check, capture_output=capture_output, text=True)

    # Get "args" to pass into the subprocess to run a command on this instance
    def _get_proc_args(self, cmd):
        if self.connect == 'ssh':
            cmd = cmd.replace('"', '\\"')
            return f'ssh -o "StrictHostKeyChecking=no" "{self.user_address}" "{cmd}"'
        else:
            return cmd

    # SCP a file to/from the node.
    def _scp(self, fp_from, fp_to):
        cmd = f'scp "{fp_from}" "{fp_to}"'
        self.log.debug(cmd)
        return subprocess.run(cmd, shell=True, check=True, capture_output=self.cluster.quiet)

    # Upload a file from the local machine to the instance.
    def _upload(self, fp_local, fp_remote):
        return self._scp(fp_local, f'{self.user_address}:{fp_remote}')

    # Download a file from the instance to the local machine.
    def _download(self, fp_remote, fp_local):
        self._sh(f'mkdir -p {os.path.dirname(fp_local)}')
        return self._scp(f'{self.user_address}:{fp_remote}', fp_local)

    # ensure all software is up-to-date
    def update(self):
        self.log.info(f'updating packages...')
        self._apt('apt-get update')
        self._apt('apt-get upgrade')
        self._apt('apt-get dist-upgrade')

        self.log.info(f'cleaning up...')
        self._apt(f'apt autoremove')

    # Reboot the instance
    def reboot(self):
        self.log.info(f'rebooting...')
        self.exec('sudo reboot &')

    # Copy SSH key from localhost
    def ssh_copy_id(self, fp = '~/.ssh/id_rsa'):
      if self.connect != 'ssh':
          self.log.warning(f'will not add SSH key because connection type is {self.connect}')
          return
      fp = os.path.expanduser(fp)
      if not os.path.isfile(fp):
          self.log.warning(f'skipping adding SSH key because nothing exists at {fp}')
          return
      self.log.info(f'configuring SSH access for {fp} to {self.user_address}...')
      subprocess.run(f'ssh-copy-id -i {fp} {self.user_address}', shell=True, check=True)

    # Get the IPv4 address of a given interface
    def _get_network_address(self, interface, itype = 'inet'):
        self.log.debug(f'examining interface {interface} for {itype}...')
        cmd = f"/sbin/ifconfig {interface} | grep '{itype} ' || echo ''"
        res = self.exec(cmd, capture_output=True).stdout
        if len(res) <= 0: return None
        net = [x for x in res.split(' ') if len(x) > 0]
        if len(net) < 2 or net[0] != itype:
            raise Exception(f'ifconfig returned unknown syntax: {res}')
        return net[1]

    # Get the names of all network interfaces
    def _get_network_interfaces(self):
        if self._network_interfaces: return self._network_interfaces
        cmd = "/sbin/ip -o link show"
        if_matcher = re.compile('(?P<num>[0-9]+):\s*(?P<interface>[0-9a-z]*):')
        res = self.exec(cmd, capture_output=True).stdout.split('\n')
        self._network_interfaces = []
        for line in res:
            match = if_matcher.match(line)
            if not match or not match.group('interface'): continue
            interface = match.group('interface')
            if interface == 'lo': continue
            self._network_interfaces.append(interface)
        return self._network_interfaces

    # Get the name of the first interface connected to the internet, or with an explicit IP.
    def _get_best_interface(self, ip_address = None):
        self.log.debug(f'attempting to find an interface (ip: {ip_address})')
        for interface in self._get_network_interfaces():
            addr = self._get_network_address(interface)
            if not ip_address or addr == ip_address:
                self.log.debug(f'"{interface}" matches "{ip_address}"')
                return interface
        return None

    def print_network_interfaces(self):
        for interface in self._get_network_interfaces():
            addr = self._get_network_address(interface)
            self.log.info(f'{interface} = {addr}')

    # Helper to build apt commands.
    def _apt(self, cmd, values = ''):
        flags = '-y -qq' if self.cluster.quiet else '-y'
        return self.exec(f'sudo {cmd} {flags} {values}')

    # def configure(self):
    #     self.log.info('determining join command...')
        # kubeadm token create --print-join-command
        # sudo ^^^
        # kc label nodes spellbook-den home-cluster/beacon=true
        # [Service]
        # Environment="KUBELET_EXTRA_ARGS=--node-labels=home-cluster/beacon=true,label2=value2
            # --register-with-taints=foo=bar:NoSchedule"

    # c.f. https://blog.hypriot.com/post/setup-kubernetes-raspberry-pi-cluster/
    # c.f. https://kubecloud.io/setting-up-a-kubernetes-1-11-raspberry-pi-cluster-using-kubeadm-952bbda329c8

