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

    def _configure_xscreensaver(self):
        self.log.info(f'configuring xscreensaver...')
        self.node._upload('.xscreensaver')

        xss = self.cfg['xscreensaver']
        self.node._ssh(f'sed -i "s/TIMEOUT/{xss["timeout"]}/g" .xscreensaver')
        self.node._ssh(f'sed -i "s/MODE/{xss["mode"]}/g" .xscreensaver')

    def _setup_xscreensaver(self):
        if self.cfg:
            self.log.info(f'installing xscreensaver...')
            self.node._apt(f'install', 'xscreensaver')
        else:
            self.log.info(f'removing xscreensaver...')
            self.node._apt(f'remove', 'xscreensaver')
            self.node._ssh('rm .xscreensaver')

    def setup(self):
        if not self.cfg:
            self.node._ssh(f'rm {self.path.fp_autostart} || true')
            self.node._ssh(f'rm kiosk.sh || true')

        self._setup_xscreensaver()

    def configure(self):
        if not self.cfg: return

        self.node._upload('kiosk.sh')

        self.log.info(f'setting kiosk url: "{self.url}"...')
        self.node._autostart(f'/home/pi/kiosk.sh \'{self.url}\' \'{self.cfg["chromium_flags"]}\'')

        self._configure_xscreensaver()
