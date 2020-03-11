# Tiny Cluster
CLI + yaml for the configuration of an at-home Kubernetes fleet with one or more Raspberry Pis.

[Read the Blog Post](https://www.technicallywizardry.com/raspberry-pi-config-management-kubernetes/) for examples, screenshots, etc. Please open a Github issue for any problems.

## Practical Usage

_Some configuration requried (see [Getting Started](#getting-started)). Assume you've aliased `ln -sf ./tiny-cluster.py /usr/local/bin/tc` and your `contexts` directiry lives within the `pwd`._

Create Kubernetes cluster, installing kubeadm with weave/flannel and NFS support enabled per `yaml` config:

`tc master create`

Create another node, "rpi", installing docker/kubeadm and using fixed IP defined in the `yaml`:

`tc rpi create`

Join the cluster:

`tc rpi join`

Add some labels to the node per the `yaml` config:

`tc rpi label`

Set up the node as a "Kiosk", showing a permanent Chromium browser pointed at a web URL:

`tc rpi configure`

SSH into one of the nodes:

`tc rpi ssh`

Reboot a node:

`tc rpi reboot`

Create a second cluster:

`tc -c second-cluster master create`

## Features

- Use `yaml` to provide configuration as code.
- Set up a brand new Raspberry Pi with a single command.
- Provide "Kiosk Mode" (turn a Raspberry Pi into a dedicated web browser).
- Keep the entire cluster of devices up-to-date using stateless technologies like Docker and Kubernetes.
- Avoid of one-off scripts and backups.
- Easy to integrate with [Home Assistant](https://www.home-assistant.io/)

## What it Does

* Enable password-less SSH access
* Perform system updates (`apt`)
* Assign a static IP address
* Install Chromium Kiosk scripts (if Kiosk mode enabled)
* Install kubeadm, network add-ons, and NFS
* Apply labels to nodes
* Provide a simple interface for other advanced management features.

## With Many Thanks...

This repo is a tool I cobbled together over the course of a good year or so. I am placing it here in the hopes that it will be useful to others. But much of the work comes from sources like these:

- [Alex Ellis](https://www.alexellis.io/) for [his work getting K8s on Raspbian](https://gist.github.com/alexellis/fdbc90de7691a1b9edb545c17da2d975).
- [How to Set Up a Raspberry Pi Cluster](https://blog.hypriot.com/post/setup-kubernetes-raspberry-pi-cluster/)
- [Kubeadm on Raspberry Pi](https://kubecloud.io/setting-up-a-kubernetes-1-11-raspberry-pi-cluster-using-kubeadm-952bbda329c8)
- [Baremetal K8s with Kubeadm](https://medium.com/@kvaps/creating-high-available-baremetal-kubernetes-cluster-with-kubeadm-and-keepalived-simplest-guide-71766d5e25ae)
- [K8s on Pi](https://medium.com/nycdev/k8s-on-pi-9cc14843d43)
- [Kiosk mode for Home Assistant](https://gist.github.com/ciotlosm/1f09b330aa5bd5ea87b59f33609cc931)
- [Argbash](https://argbash.io/generate)
- [What are the Raspberry Pi OUIs](https://raspberrypi.stackexchange.com/questions/28365/what-are-the-possible-ouis-for-the-ethernet-mac-address)?
- [Disabling Swap in Linux](https://serverfault.com/questions/684771/best-way-to-disable-swap-in-linux)

# Getting Started

## Terminology

* The `controlling` computer is, presumably, the computer you're currently using. It's what will run the commands.
* The `master` and `nodes` are Kubernetes terms. Your cluster will first need to have a master set up, and then the nodes can join the cluster.

## Pre-Requisites

* Your current "controlling" (this) computer must [have Python3 installed](https://realpython.com/installing-python/).
* One or more Raspberry Pis with [`ssh` enabled](https://www.raspberrypi.org/documentation/remote-access/ssh/), connected to the same network as the controlling computer.

## Quick Start

_Note: any time you use `tiny-cluster.py` below, you can append `-l DEBUG` to change the log mode to be more verbose. You can also run ./tiny-cluster.py --help for assistance with any command._

* Clone this repository: `git clone git@github.com:zaneclaes/tiny-cluster.git`
* Install the required python packages: `pip3 install pyyaml deepmerge argparse`
* Run `cd tiny-cluster` and `./tiny-cluster.py setup` to scan the local network and follow the prompts.

If a Raspberry Pi is connected to the network, it should be discovered and walk you through the setup. Note that the auto-detect feature requires the [`arp` tool](https://www.computerhope.com/unix/arp.htm). The auto-detect feature is generally less well-tested than the following manual setup steps, and should presently be considered "beta."

## Manual Setup

See the `defaults.yaml` file in this repository for a sense of all the options available. Tiny Cluster will look in `contexts/home.yaml` for your configuration (do not modify `defaults.yaml`). If you want to run Tiny Cluster in multiple locations, see "Advanced Configurations" below.

The following is an sample `contexts/home.yaml` file which is used in the example setup steps below. Key concepts to understand:

* It assumes you know the IP addresses of the Raspberry Pis you wish to configure (192.168.0.1, etc.). Tiny Cluster will ensure these IP addreses are static at a later point.
* It defines a Kubernetes master, as well as two nodes (if you look closely, you'll note the master actually shares an IP address with one of the nodes, which implies that the master also acts as a node).
* Both of the two nodes will have Kiosk mode enabled, which means that they will open Chromium on boot to the URL `http://192.168.0.1:8123/lovelace/home?kiosk` and `http://192.168.0.1:8123/lovelace/rpi?kiosk`, respectively.
* The `rpi` node will have a Kubernetes label of `tiny-cluster/node-pi-beacon=true`. This is helpful in the later steps for deploying a Docker container to this node.

```
kubernetes:
  master:
    address: 192.168.0.1
    connect: ssh
    username: pi

nodes:
  192.168.0.1:
    name: main
    kiosk:
      url_slug: home

  192.168.0.2:
    name: rpi
    labels:
    - tiny-cluster/node-pi-red=true
    kiosk:
      url_slug: rpi

defaults:
  kiosk:
    url_base: http://192.168.0.1:8123/lovelace/
    url_query_params:
    - kiosk
    url_slug: null
```

### Master Setup

The following command will install `kubeadm` and then perform the necessary configuration steps:

`./tiny-cluster.py --node master create`

The configuration steps are equivalent to running the following commands:

* `./tiny-cluster.py master create_context`: generate a `.kube/home.conf` configuration file which is downloaded to the controlling computer so that it may subsequently access the cluster.
* `./tiny-cluster.py master install_network_add_on`: Install `flannel` or `weave`
* `./tiny-cluster.py master configure_nfs`: Create a network file system at `/mnt/tiny-cluster` which may be accessed by the local network
* `./tiny-cluster.py master untaint`: If this master is also a `node` (the same IP is used within the `nodes` condfig), then remove the `master` taint.

### Node Setup

The folloting command will set up the `rpi` node, as defined in the above configuration:

`/tiny-cluster.py rpi create`

It begins by updating the device, assigning the static IP address, and installing the required scripts. Then it performs commands equivalent to running the following:

* `./tiny-cluster.py rpi configure`: write the configuration files (e.g., the kiosk startup URL) to the device and join the Kubernetes cluster.
* `./tiny-cluster.py rpi update`: make sure all packages are up-to-date.
* `./tiny-cluster.py rpi reboot`: restart the device.

The following additional commands may be useful:

* `./tiny-cluster.py rpi ssh`: SSH into the device
* `./tiny-cluster.py rpi join`: (Re)join the Kubernetes cluster
* `./tiny-cluster.py rpi label`: (Re)label the node in the cluster

## Deploying Docker Containers

Included in the `./kubernetes` folder are a number of sample deployments for Docker containers I have created.

For example, you can use `kubectl apply -f ./kubernetes/rode-red.yaml` to deploy Node Red. In the above example configuration file, we used the label `tiny-cluster/node-pi-red=true`, which is what tells Kubernetes to deploy to that node in particular.

The following sample deployments are included:

* `./kubernetes/node-red.yaml`: [Node Red](https://nodered.org/)
* `./kubernetes/beacon.yaml`: A [BTLE beacon that advertises the presence of your phone via MQTT](https://github.com/zaneclaes/node-pi-beacon). Useful in conjunction with Home Assistant to determine which room you are in.
* `./kubernetes/obd-monitor.yaml`: [OBD Monitor](https://github.com/zaneclaes/node-pi-obd-monitor). Useful for monitoring vehicles.

## Advanced Configurations

You may have more than one configuration, known as a Context. The default context is `home`, thus the fact that your configuration usually resides at `contexts/home.yaml`. If you were to create a second file named `contexts/work.yaml`, then you could run `./tiny-cluster.py -c work master create` (or any other command), where the context name is the first argument.

Configurations are loaded in the following way:

* `defaults.yaml` is loaded.
* `contexts/the-context-name.yaml` is merged on top of those values.
* From the resulting config, the `defaults` entries are merged with the specific values provided within `kubernetes` and `nodes`. For example, in the above sample configuration, there is no need to re-define the `url_base` for the kiosk in each node, because it is inherited from `defaults.kiosk`.

### Other Linux Flavors

Tiny Cluster supports using a Kubernetes master IP that is not a Raspberry Pi. It has specifically been tested on Ubuntu 18.04. It should generally work with Debian-flavors, but has not been tested beyond that. However, it may require some manual tuning. For example:

* Your SSH user must be able to sudo without a password, [like this for Ubuntu](https://phpraxis.wordpress.com/2016/09/27/enable-sudo-without-password-in-ubuntudebian/)
* You may wish to [make systemd the default](https://kubernetes.io/docs/setup/production-environment/container-runtimes/).

Also, be aware that Tiny Cluster will symlink `~/.kube/config` to the config file for the kubeadm master it creates.

### Advanced DNS Options

```
defaults:
  node:
    dns: 192.168.0.1 # Set the DNS server
    hdmi: false # Turn off the HDMI
    interface: wlan0 # Default network interface
    usb_ethernet: true # Turn on USB/Ethernet card
```

### Advanced Kiosk Options

See the comments in `defaults.yaml`

# Supported With...

## Tested OSs

- Raspbian Jessie
- Raspbian Buster

## Tested On

- Raspberry Pi 4 B+
- Raspberry Pi 3 B+
- Raspberry Pi 3 B
- Raspberry Pi Zero W

