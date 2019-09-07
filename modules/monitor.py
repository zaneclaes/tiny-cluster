#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger

class Monitor():
    def __init__(self, node, monitor_cfg):
        self.cfg = monitor_cfg
        self.node = node
        self.log = node.log
        if not self.cfg: return
        self.log.debug(f'loaded monitor')

    # Install/uninstall monitor with the appropriate options
    def setup(self):
        mosquitto_deps = 'libmosquitto-dev mosquitto mosquitto-clients libmosquitto1'
        monitor_deps = 'git bluez-hcidump bc'

        self.node._ssh('rm -rf monitor || true')
        if not self.cfg:
            self.node._apt('remove', mosquitto_deps)
            self.node._apt('remove', monitor_deps)
            return
        # c.f. https://github.com/andrewjfreyer/monitor#configuration-and-setup
        self.log.info(f'installing mosquitto...')
        self.node._ssh('wget -q http://repo.mosquitto.org/debian/mosquitto-repo.gpg.key')
        self.node._ssh(f'sudo apt-key add -qq mosquitto-repo.gpg.key {self.stdout}')
        # self.node._ssh('cd /etc/apt/sources.list.d/')
        self.node._ssh('sudo wget -q http://repo.mosquitto.org/debian/mosquitto-stretch.list')
        self.node._ssh(f'sudo apt-cache search -qq mosquitto {self.node.stdout}')
        self.node._apt('update')
        self.node._apt('install', f'-f {mosquitto_deps}')
        self.node._ssh('rm -rf mosquitto-*')

        # c.f. https://github.com/andrewjfreyer/monitor#setup-monitor
        self.log.info(f'installing monitor...')
        self.node._apt('install', monitor_deps)
        self.node._ssh('git clone -q git://github.com/andrewjfreyer/monitor')
        self.node._ssh('cd monitor/ && echo "y" | bash monitor.sh || true')

    def configure(self):
        if not self.cfg: return

        self.log.info('configuring preferences...')
        ip = ha.cfg["ip"].replace(".", "\\.")
        self.node._ssh(f'sed -i "s/0\\.0\\.0\\.0/{ip}/" monitor/mqtt_preferences')
        prefs = {
          'mqtt_user': 'username', 'mqtt_password': 'password',
          'mqtt_topicpath': 'monitor', 'mqtt_publisher_identity': "''"}
        for p in prefs:
            self.node._ssh(f'sed -i "s/{p}={prefs[p]}/{p}={cfg["monitor"][p]}/" monitor/mqtt_preferences')

        self.log.info('registering blacklist...')
        for device in cfg['monitor']['blacklist']:
            self.node._ssh(f'sudo echo "{device["mac"]} {device["name"]}" >> monitor/address_blacklist')

        self.log.info('registering beacons...')
        fp_kba = 'monitor/known_beacon_addresses'
        for node_name in nodes:
            if node_name == self.name: continue
            node = nodes[node_name]
            if not node.cfg['monitor']: continue
            self.log.info(f'detecting beacon for node: {node_name}...')
            bt_mac = kiosk._get_bt_mac_addr()
            self.log.info(f'found mac address "{bt_mac}" for node: {node_name}')
            self.node._ssh(f'sudo echo "{bt_mac} {node_name}" >> {fp_kba}')

        for beacon in cfg['monitor']['beacons']:
            self.node._ssh(f'sudo echo "{beacon["mac"]} {beacon["name"]}" >> {fp_kba}')

        self.log.info('registering devices...')
        fp_ksa = 'monitor/known_static_addresses'
        for device in cfg['monitor']['devices']:
            self.node._ssh(f'sudo echo "{device["mac"]} {device["name"]}" >> {fp_ksa}')

        self.log.info('backing up monitor config...')
        for cfg_file in cfg['monitor']['config_files']:
            self.node._backup(f'monitor/{cfg_file}')

        self.log.info('restarting monitor...')
        self.node._ssh('sudo service monitor restart')

        # self.log.warning(f'for customization, edit files in {dir_local} and then run: `{script} {self.name} restore`')