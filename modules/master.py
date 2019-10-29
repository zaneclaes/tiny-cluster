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
    def install_nfs(self, nfs_dir = 'tiny-cluster', allow_ip = '*'):
        nfs_path = f'/mnt/{nfs_dir}'
        nfs_allow = f'{nfs_path} {allow_ip}'
        self.exec(f'sudo mkdir -p {nfs_path}')
        self.exec(f'sudo chown nobody:nogroup {nfs_path}')
        self.exec(f'sudo chmod 777 {nfs_path}')
        self.exec(f'(cat /etc/exports | grep "{nfs_path}") || echo "{nfs_path}(rw,sync,no_subtree_check) >> /etc/exports"')
        self.exec(f'sudo exportfs -a')
        self.exec(f'sudo systemctl restart nfs-kernel-server')

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

        # KC_ENV="van"
        # sudo swapoff -a && sudo kubeadm init --apiserver-advertise-address=192.168.1.100 --upload-certs
        # sudo cp /etc/kubernetes/admin.conf $HOME/.kube/${KC_ENV}.conf && sudo chown $(id -u):$(id -g) $HOME/.kube/${KC_ENV}.conf
        # kubectl apply -f "https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')&env.IPALLOC_RANGE=10.32.0.0/16"
        # sudo sysctl net.bridge.bridge-nf-call-iptables=1
        # sed -i "s/kubernetes/house/g" $HOME/.kube/house.conf
        # export KUBECONFIG=$HOME/.kube/house.conf:$HOME/.kube/config
        # kubectl taint nodes house node-role.kubernetes.io/master-
