#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess

"""
Manage Kiosk settings
"""
class Kubernetes():
    def __init__(self, node, kubernetes_config):
        self.cfg = kubernetes_config
        self.node = node
        self.log = node.log
        if not self.cfg: return

    # https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/
    # https://medium.com/@kvaps/creating-high-available-baremetal-kubernetes-cluster-with-kubeadm-and-keepalived-simplest-guide-71766d5e25ae
    # https://medium.com/nycdev/k8s-on-pi-9cc14843d43
    # def _install_master(self):
        # sudo swapoff -a && sudo kubeadm init --apiserver-advertise-address=192.168.1.100 --upload-certs
        # kubectl apply -f "https://cloud.weave.works/k8s/net?k8s-version=$(kubectl version | base64 | tr -d '\n')"
        # sudo sysctl net.bridge.bridge-nf-call-iptables=1
        # sudo cp /etc/kubernetes/admin.conf $HOME/.kube/house.conf && sudo chown $(id -u):$(id -g) $HOME/.kube/house.conf
        # sed -i "s/kubernetes/house/g" $HOME/.kube/house.conf
        # export KUBECONFIG=$HOME/.kube/house.conf:$HOME/.kube/config
        # kubectl taint nodes house node-role.kubernetes.io/master-

    def configure(self):
        self.log.info('determining join command...')
        # kubeadm token create --print-join-command
        # sudo ^^^
        # kc label nodes spellbook-den home-cluster/beacon=true
        # [Service]
        # Environment="KUBELET_EXTRA_ARGS=--node-labels=home-cluster/beacon=true,label2=value2
            # --register-with-taints=foo=bar:NoSchedule"

    # c.f. https://blog.hypriot.com/post/setup-kubernetes-raspberry-pi-cluster/
    # c.f. https://kubecloud.io/setting-up-a-kubernetes-1-11-raspberry-pi-cluster-using-kubeadm-952bbda329c8
    def install(self):
        self.log.info('installing kubeadm...')

        self.node._ssh('curl -sSL get.docker.com | sh && sudo usermod pi -aG docker')
        self.node._ssh('sudo dphys-swapfile swapoff && sudo dphys-swapfile uninstall && sudo update-rc.d dphys-swapfile remove')

        self.node._ssh('sudo cp /boot/cmdline.txt /boot/cmdline_backup.txt')
        self.node._ssh('echo "$(head -n1 /boot/cmdline.txt) cgroup_enable=cpuset cgroup_enable=memory" | sudo tee /boot/cmdline.txt')

        self.node._ssh(' && '.join([
            'curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -',
            'echo "deb http://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list'
        ]))
        self.node._apt('update')
        self.node._apt('install', 'kubeadm')
