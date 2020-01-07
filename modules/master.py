#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from modules.instance import *

"""
Master node
"""
class Master(Instance):
    def __init__(self, cluster, master_cfg):
        super(Master, self).__init__(cluster, 'master', master_cfg)
        self.log.debug(f'loaded master at {self.user_address}')

    # Command for a node to join this cluster.
    def _get_join_command(self):
        return self.exec('kubeadm token create --print-join-command', capture_output=True).stdout

    def print_join_command(self):
        print(self._get_join_command())

    # https://vitux.com/install-nfs-server-and-client-on-ubuntu/
    def install_nfs(self):
        if not self.cluster.nfs or len(self.cluster.nfs['directory']) <= 0: return
        nfs_dir = self.cluster.nfs['directory']
        nfs_path = f'/mnt/{nfs_dir}'
        nfs_allow = nfs_path + ' ' + self.cluster.nfs['allow_ip']
        self.exec(f'sudo mkdir -p {nfs_path}')
        self.exec(f'sudo chown nobody:nogroup {nfs_path}')
        self.exec(f'sudo chmod 777 {nfs_path}')
        self.exec(f'(cat /etc/exports | grep "{nfs_allow}") || echo "{nfs_allow}(rw,sync,no_subtree_check) >> /etc/exports"')
        self.exec(f'sudo exportfs -a')
        self.exec(f'sudo systemctl restart nfs-kernel-server')

    # If the master is ALSO a node, returns that node. Otherwise, none.
    @property
    def _node(self):
        if not self.address in self.cluster.nodes: return None
        return self.cluster.nodes[self.address]

    # Create the Kubernetes cluster via Kubeadm, and run all install/config steps
    def create(self):
        self.ssh_copy_id()
        init_flags = f'--apiserver-advertise-address={self.address} --upload-certs'
        if self.cluster.network_add_on == 'flannel':
            init_flags += ' --pod-network-cidr=10.244.0.0/16'
        self.log.info('creating cluster with kubeadm...')
        self.exec(f'sudo swapoff -a && sudo kubeadm init {init_flags}')
        self.create_context()
        self.install_network_add_on()
        self.install_nfs()
        self.untaint()

    # Create and download a context config file for this cluster.
    def create_context(self):
        fp = f'.kube/{self.cluster.context}.conf'
        self.log.info(f'creating cluster config file: {fp}...')
        cf =  f'/home/{self.username}/{fp}'
        self.exec(f'mkdir -p /home/{self.username}/.kube')
        self.exec(f'sudo cp /etc/kubernetes/admin.conf {cf} && sudo chmod +rw {cf}')
        self.exec(f'sed -i s/kubernetes/{self.cluster.context}/g {cf}')
        self._download(cf, f'$HOME/{fp}')

    # Remove the master-node taint.
    def untaint(self):
        n = self._node
        if not n: return
        self.log.info(f'untaining master node "{n.name}"...')
        self.exec(f'kubectl taint nodes {n.name} node-role.kubernetes.io/master-')

    # Install the networking add-on, if requested
    def install_network_add_on(self):
        if not self.cluster.network_add_on: return
        self.log.info(f'installing network add on: {self.cluster.network_add_on}')
        if self.cluster.network_add_on == 'flannel':
          self.exec('kubectl apply -f https://raw.githubusercontent.com/coreos/flannel/2140ac876ef134e0ed5af15c65e414cf26827915/Documentation/kube-flannel.yml')

    # https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/
    # https://medium.com/@kvaps/creating-high-available-baremetal-kubernetes-cluster-with-kubeadm-and-keepalived-simplest-guide-71766d5e25ae
    # https://medium.com/nycdev/k8s-on-pi-9cc14843d43
    # def _install_master(self):
        # UBUNTU:
        # sudo apt install docker.io && sudo systemctl enable docker
        # curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add
        # sudo apt-add-repository "deb http://apt.kubernetes.io/ kubernetes-xenial main"
        # sudo apt install kubeadm
        # Permanently disable swap: https://serverfault.com/questions/684771/best-way-to-disable-swap-in-linux

        # kubectl apply -f "https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')&env.IPALLOC_RANGE=10.32.0.0/16"
        # sudo sysctl net.bridge.bridge-nf-call-iptables=1
        # kubectl taint nodes house node-role.kubernetes.io/master-
