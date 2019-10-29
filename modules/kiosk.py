#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess

"""
Manage Kiosk settings
"""
class Kiosk():
    def __init__(self, node, kiosk_cfg):
        self.cfg = kiosk_cfg
        self.node = node
        self.log = node.log
        if not self.cfg: return

        self.url_slug = self.cfg["url_slug"] if self.cfg["url_slug"] else self.node.name
        self.url = f'{self.cfg["url_base"]}{self.url_slug}'
        if len(self.cfg["url_query_params"]) > 0:
            qps = "&".join(self.cfg["url_query_params"])
            self.url += f'?{qps}'
        self.log.debug(f'loaded kiosk [{self.url}]')

    def setup(self):
        if self.cfg:
            self.log.info(f'installing xscreensaver...')
            self.node._apt(f'apt-get install', 'xscreensaver unclutter')
        else:
            self.log.info(f'removing xscreensaver...')
            self.node._apt(f'apt-get remove', 'xscreensaver unclutter')
            self.node.exec('rm .xscreensaver')
            self.node.exec(f'rm kiosk.sh || true')

    def configure(self):
        if not self.cfg: return

        self.node._upload_rp_file('kiosk.sh')
        self.node.exec('chmod +x kiosk.sh')

        self.node._autostart('xscreensaver &')
        if self.cfg['unclutter']:
            self.node._autostart(f'unclutter -idle {self.cfg["unclutter"]} -root &')

        self.log.info(f'configuring xscreensaver...')
        self.node._upload_rp_file('.xscreensaver')

        xss = self.cfg['xscreensaver']
        self.node.exec(f'sed -i "s/TIMEOUT/{xss["timeout"]}/g" .xscreensaver')
        self.node.exec(f'sed -i "s/MODE/{xss["mode"]}/g" .xscreensaver')

        self.log.info(f'setting kiosk url: "{self.url}"...')
        self.node._autostart(f'{self.node.dir_home}/kiosk.sh "{self.url}" -f "{self.cfg["chromium_flags"]}"')
