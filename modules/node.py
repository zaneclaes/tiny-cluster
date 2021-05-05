#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger
from modules.host import *
from modules.instance import *
from modules.master import *

"""
Manage a Node (each instance of this class controls a single device)
"""
class Node(Instance):
    def __init__(self, cluster, node_cfg):
        if not 'name' in node_cfg:
            raise Exception(f'node configuration missing name: {node_cfg}')
        if len(node_cfg['name']) < 3:
            raise Exception(f'node name too short: {node_cfg["name"]}')
        super(Node, self).__init__(cluster, node_cfg['name'], node_cfg)
        self.orig_cfg = dict(node_cfg)
        self.dir_home = f'/home/{self.cfg["username"]}'
        self.host = Host(self, self.cfg['host'])
        self.k8s = self.cfg['kubernetes']
        self.master = Master(self) if self.k8s and self.k8s['master'] else None
        self.log.debug(f'loaded node {self.user_address} [{self.name}.local] {self.cfg}')

    # EVERYTHING (setup node from scratch)
    def create(self):
        self.log.info('creating...')
        self._ssh_copy_id()
        self.host.create()
        if self.k8s:
            self._setup_kubeadm()
            if self.master: self.master.create()
        self.configure()
        self.reboot()

    # Fast configuration, i.e., ensure host settings, labels, etc. are correct
    def configure(self):
        self.log.info('configuring...')
        self.host.configure()
        if not self.master: self.join()
        self.label()

    # (Re)join the Kubernetes cluster
    def join(self):
        if self.master:
            self.log.info('The master node cannot join a cluster.')
            return
        if not self.cluster.master:
            self.log.error('Nothing to join: there is no master Kubernetes node.')
            return
        self.log.info('leaving cluster...')
        self.exec('sudo kubeadm reset -f || true')

        self.log.info('joining cluster...')
        cmd = self.cluster.master._get_join_command()
        if len(cmd) <= 0: raise Exception('failed to retrieve kubeadm join command')
        self.exec(f'sudo {cmd}')

    # Add Kubernetes labels to the node.
    def label(self):
        labels = set(self.k8s['kubernetes']['labels'])
        labels.add(f'tiny-cluster/name={self.name}')
        if self.master: labels.add('tiny-cluster/master=true')

        for label in labels:
            self.log.info(f'applying label "{label}"...')
            self.cluster.master.exec(f'kubectl label nodes {self.name} {label} --overwrite')
