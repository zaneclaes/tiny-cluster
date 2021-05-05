#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess, socket
from modules.instance import *

"""
Master node
"""
class Master():
    def __init__(self, node):
        self.node = node
        self.log = node.log
        self.exec = node.exec
        self.cluster = node.cluster
        self.log.debug(f'loaded master at {node.user_address}')

    # Command for a node to join this cluster.
    def _get_join_command(self):
        cmd = 'sudo kubeadm token create --print-join-command'
        return self.node.exec(cmd, capture_output=True).stdout

    def print_join_command(self):
        print(self._get_join_command())

    # If the master is ALSO a node, returns that node. Otherwise, none.
    @property
    def _node(self):
        if not self.address in self.cluster.nodes: return None
        return self.cluster.nodes[self.address]

    # Create the Kubernetes cluster via Kubeadm, and run all install/config steps
    def create(self):
        self._ssh_copy_id()
        self._setup_kubeadm()
        init_flags = f'--apiserver-advertise-address={self.address} --upload-certs'
        if self.cluster.network['add-on'] == 'flannel':
            init_flags += ' --pod-network-cidr=' + self.cluster.network['ip-range']
        self.log.info('creating cluster with kubeadm...')
        self.exec(f'sudo swapoff -a && sudo kubeadm init {init_flags}')
        self.create_context()
        self.install_network_add_on()
        self.untaint()

    # Create and download a context config file for this cluster.
    def create_context(self):
        name = self.cluster.env
        fp = f'.kube/{name}.conf'
        self.log.info(f'creating cluster config file: {fp}...')
        cf =  f'/home/{self.username}/{fp}'
        self.exec(f'mkdir -p /home/{self.username}/.kube')
        self.exec(f'sudo cp /etc/kubernetes/admin.conf {cf} && sudo chmod +rw {cf}')
        self.exec(f'sed -i s/kubernetes/{name}/g {cf}')
        self.exec(f'ln -sf {cf} /home/{self.username}/.kube/config')
        self._download(cf, f'$HOME/{fp}')

    # Install the networking add-on, if requested
    def install_network_add_on(self):
        ao = self.cluster.network['add-on']
        if not ao: return
        self.cluster.set_context()
        if ao == 'flannel':
            af = 'https://github.com/coreos/flannel/raw/master/Documentation/kube-flannel.yml'
        elif ao == 'weave':
            af = "https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')&env.IPALLOC_RANGE=" + self.cluster.network['ip-range']
        else:
            raise Exception(f'Unsupported network add-on: {ao}')
        self.log.info(f'installing network add on: {af}')
        self.exec(f'kubectl apply -f "{af}"')

    # https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/
    # https://medium.com/@kvaps/creating-high-available-baremetal-kubernetes-cluster-with-kubeadm-and-keepalived-simplest-guide-71766d5e25ae
    # https://medium.com/nycdev/k8s-on-pi-9cc14843d43
