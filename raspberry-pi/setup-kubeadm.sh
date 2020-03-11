#!/bin/sh

# Install Docker
if [[ ! $(which docker) ]]; then
  echo "installing docker..."
  curl -sSL get.docker.com | sh && sudo usermod pi -aG docker
else
  echo "docker already installed."
fi

# Disable Swap
sudo dphys-swapfile swapoff && \
  sudo dphys-swapfile uninstall && \
  sudo systemctl disable dphys-swapfile

flags="cgroup_enable=cpuset cgroup_enable=memory"
if grep -q "$flags" /boot/cmdline.txt; then
  echo "boot flags '$flags' already configured."
else
  echo "Adding '$flags' to /boot/cmdline.txt"
  sudo cp /boot/cmdline.txt /boot/cmdline_backup.txt
  orig="$(head -n1 /boot/cmdline.txt) $flags"
  echo $orig | sudo tee /boot/cmdline.txt
fi

# Add repo list and install kubeadm
if [[ ! $(which kubeadm) ]]; then
  echo "installing kubeadm..."
  curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add - && \
    echo "deb http://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list && \
    sudo apt-get update -q && \
    sudo apt-get install -qy kubeadm
else
  echo "kubeadm already installed."
fi

if [[ ! $(which exportfs) ]]; then
  sudo apt install nfs-kernel-server
else
  echo "nfs-kernel-server already installed."
fi
