# Home Cluster
One-touch installation and configuration tool for managing the configuration of one or more Raspberry Pis.

This project is WIP, but everything described below should function. Please open a Github issue for any problems.

## At-a-Glance

* **Kiosk** mode will make the node into a dedicated Chromium browser for a web interface.
* **Docker** images are used to deploy features.
* **Kubernetes** connects all the devices together into a single mesh.

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
* Install the required python packages: `pip3 install pyyaml`
* Run `cd tiny-cluster` and `./tiny-cluster.py setup` to scan the local network and follow the prompts.

If a Raspberry Pi is connected to the network, it should be discovered and walk you through the setup. Note that the auto-detect feature requires the [`arp` tool](https://www.computerhope.com/unix/arp.htm). The auto-detect feature is generally less well-tested than the following manual setup steps, and should presently be considered "beta."

## Manual Setup

See the `defaults.yaml` file in this repository for a sense of all the options available. Tiny Cluster will look in `contexts/home.yaml` for your configuration (do not modify `defaults.yaml`). If you want to run Tiny Cluster in multiple locations, see "Advanced Configurations" below.

The following is an sample `contexts/home.yaml` file which is used in the example setup steps below. Key concepts to understand:

* It assumes you know the IP addresses of the Raspberry Pis you wish to configure (192.168.0.1, etc.). Tiny Cluster will ensure these IP addreses are static at a later point.
* It defines a Kubernetes master, as well as two nodes (if you look closely, you'll note the master actually shares an IP address with one of the nodes, which implies that the master also acts as a node).
* Both of the two nodes will have Kiosk mode enabled, which means that they will open Chromium on boot to the URL `http://192.168.0.1:8123/lovelace/home?kiosk` and `http://192.168.0.1:8123/lovelace/spellbook?kiosk`, respectively.
* The `spellbook` node will have a Kubernetes label of `tiny-cluster/node-pi-beacon=true`. This is helpful in the later steps for deploying a Docker container to this node.

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
    name: spellbook
    labels:
    - tiny-cluster/node-pi-red=true
    kiosk:
      url_slug: spellbook

defaults:
  kiosk:
    url_base: http://192.168.0.1:8123/lovelace/
    url_query_params:
    - kiosk
    url_slug: null
```

### Master Setup

The following command will install `kubeadm` and then perform the necessary configuration steps:

`./tiny-cluster.py master create`

The configuration steps are equivalent to running the following commands:

* `./tiny-cluster.py master create_context`: generate a `.kube/home.conf` configuration file which is downloaded to the controlling computer so that it may subsequently access the cluster.
* `./tiny-cluster.py master install_network_add_on`: Install `flannel`
* `./tiny-cluster.py master install_nfs`: Create a network file system at `/mnt/tiny-cluster` which may be accessed by the local network
* `./tiny-cluster.py master untaint`: If this master is also a `node`, then remove the `master` taint.

### Node Setup

The folloting command will set up the `spellbook` node, as defined in the above configuration:

`/tiny-cluster.py node spellbook setup`

It begins by updating the device, assigning the static IP address, and installing the required scripts. Then it performs commands equivalent to running the following:

* `./tiny-cluster.py node spellbook configure`: write the configuration files (e.g., the kiosk startup URL) to the device and join the Kubernetes cluster.
* `./tiny-cluster.py node spellbook update`: make sure all packages are up-to-date.
* `./tiny-cluster.py node spellbook reboot`: restart the device.

The following additional commands may be useful:

* `./tiny-cluster.py node spellbook ssh`: SSH into the device
* `./tiny-cluster.py node spellbook join`: (Re)join the Kubernetes cluster
* `./tiny-cluster.py node spellbook label`: (Re)label the node in the cluster

## Deploying Docker Containers

Included in the `./kubernetes` folder are a number of sample deployments for Docker containers I have created.

For example, you can use `kubectl apply -f ./kubernetes/rode-red.yaml` to deploy Node Red. In the above example configuration file, we used the label `tiny-cluster/node-pi-red=true`, which is what tells Kubernetes to deploy to that node in particular.

The following sample deployments are included:

* `./kubernetes/node-red.yaml`: [Node Red](https://nodered.org/)
* `./kubernetes/beacon.yaml`: A [BTLE beacon that advertises the presence of your phone via MQTT](https://github.com/zaneclaes/node-pi-beacon). Useful in conjunction with Home Assistant to determine which room you are in.
* `./kubernetes/obd-monitor.yaml`: [OBD Monitor](https://github.com/zaneclaes/node-pi-obd-monitor). Useful for monitoring vehicles.

## Advanced Configurations

You may have more than one configuration, known as a Context. The default context is `home`, thus the fact that your configuration usually resides at `contexts/home.yaml`. If you were to create a second file named `contexts/work.yaml`, then you could run `./tiny-cluster work master create` (or any other command), where the context name is the first argument.

Configurations are loaded in the following way:

* `defaults.yaml` is loaded.
* `contexts/the-context-name.yaml` is merged on top of those values.
* From the resulting config, the `defaults` entries are merged with the specific values provided within `kubernetes` and `nodes`. For example, in the above sample configuration, there is no need to re-define the `url_base` for the kiosk in each node, because it is inherited from `defaults.kiosk`.

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

# Supported Devices

## Tested On

- Raspberry Pi 4 B+
- Raspberry Pi 3 B+
- Raspberry Pi 3 B
- Raspberry Pi Zero W

