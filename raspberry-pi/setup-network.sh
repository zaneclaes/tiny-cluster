#!/bin/sh
# adapted from https://kubecloud.io/setting-up-a-kubernetes-1-11-raspberry-pi-cluster-using-kubeadm-952bbda329c8

hostname=$1
ip=$2 # should be of format: 192.168.1.100
dns=$3 # should be of format: 192.168.1.1
interface=${4:-eth0}

# Change the hostname
sudo hostnamectl --transient set-hostname $hostname
sudo hostnamectl --static set-hostname $hostname
sudo hostnamectl --pretty set-hostname $hostname
sudo sed -i s/raspberrypi/$hostname/g /etc/hosts

# Set the static ip
sip="static ip_address=$ip"
if grep -q "$sip" \; then
  echo "the IP address $ip is already configured."
else
  sudo cat <<EOT >> /etc/dhcpcd.conf
interface $interface
$sip
static routers=$dns
static domain_name_servers=$dns
EOT
fi
