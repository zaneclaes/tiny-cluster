#!/usr/bin/env python3
import yaml, sys, argparse, os, re, logging, subprocess
from deepmerge import always_merger, conservative_merger
from modules.node import *
from modules.master import *
from modules.app import App
from modules.cluster import Cluster

class M8ke():
    env = None

    def get_context(self):
        c = 'kubectl config current-context'
        return subprocess.run(c, shell=True, check=True, capture_output=True, text=True).stdout.strip()

    def set_context(self, name):
        c = 'kubectl config set current-context ' + name
        subprocess.run(c, shell=True, check=True, capture_output=False)

    # Load the configuration for an enviroment from its files
    # Returns a tuple of the config for the environment + the default values for that env
    def _load_env(self, env):
        self.fp_cfg = os.path.join(self.env_dir, f'{env}.yaml')
        if os.path.isfile(self.fp_cfg):
            with open(self.fp_cfg, 'r') as stream:
                config_env = yaml.safe_load(stream)
        else:
            config_env = {}

        defs = dict(self.config_defaults)
        if 'defaults' in config_env:
            defs = always_merger.merge(defs, config_env['defaults'])

        if not 'nodes' in config_env: config_env['nodes'] = {}
        return config_env, defs

    # Set the current environment, loading its config and changing kubectl's context.
    def set_env(self, env):
        if self.env == env: return
        self.log = logging.getLogger(env)
        self.env = env
        self.config_env, defs = self._load_env(env)
        self.cluster = Cluster(self.config_env['nodes'], defs)

        # Ensure context match:
        tar_context = self.cluster.context
        if tar_context:
            cur_context = self.get_context()
            if cur_context != tar_context:
                self.log.info(f'Changing context to: {env} (was: {cur_context})')
                self.set_context(tar_context)

        self.apps = self._get_applications(env, defs)

        return True

    # Get a list of node names for a given environment.
    def _get_node_names(self, env):
        cfg, defs = self._load_env(env)
        return cfg['nodes'] if 'nodes' in cfg and cfg['nodes'] else []

    # Get the dict of app name -> app for a given environment.
    def _get_applications(self, env, defs = None):
        if not defs: cfg, defs = self._load_env(env)
        if not defs['applications']: return {}
        if defs['applications'] == '.':
            ad = self.env_dir
        else:
            ad = os.path.expandvars(defs['applications'])

        apps = {}
        for n in os.listdir(ad):
            if (not os.path.isfile(os.path.join(ad, n, 'release.yaml')) and
                not os.path.isdir(os.path.join(ad, n, 'base')) and
                not os.path.isdir(os.path.join(ad, n, env))):
                continue
            apps[n] = App(self, ad, n, env)
        return apps

    #
    def _parse_args(self, name, choices, methods):
        self.parser.add_argument(name, choices=choices)
        self.parser.add_argument('method', choices=[c for c in methods if not c.startswith('_')])

    def __init__(self):
        try:                self.fp = os.readlink(__file__)
        except OSError:     self.fp = __file__
        self.install_dir = os.path.dirname(self.fp)

        # Places where "environments" directory might be found...
        env_dir_opts = [
            os.path.expandvars("$M8KE_ENVIRONMENTS"),
            os.path.expandvars("$HOME/.m8ke"),
            os.path.expandvars("$HOME/m8ke/environments")
        ]
        self.env_dir = None
        for cd in env_dir_opts:
            if os.path.isdir(cd):
                self.env_dir = cd
                break
        if not self.env_dir:
            raise Exception(f"Could not find environments directory; looked in: {env_dir_opts}")

        # Load defaults.yaml then merge in config.yaml if it exists
        fp_def = f'{self.install_dir}/defaults.yaml'
        with open(fp_def, 'r') as stream: self.config_defaults = yaml.safe_load(stream)

        script = os.path.basename(__file__)
        log_levels = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']
        log_format = '[%(levelname)s] [%(name)s] %(message)s'

        # Attempt to pre-parse some args...
        args = sys.argv[1:]
        env = None
        i = 0
        while i < (len(args) - 1):
            if args[i] == '--env' or args[i] == '-e':
                env = args[i + 1]
                self.set_env(env)
                break
            i += 1

        self.parser = argparse.ArgumentParser(f'{script}')
        self.parser.add_argument('what', choices=['app', 'node'])
        if len(args) > 0:
            if args[0] == 'node':
                self._parse_args(args[0], self._get_node_names(env), dir(Node))
            elif args[0] == 'app':
                self._parse_args(args[0], list(self._get_applications(env)), dir(App))
        self.parser.add_argument('--env', '-e', default='default')
        self.parser.add_argument('--log-level', '-l', choices=log_levels, default='INFO')
        self.parser.add_argument('--log-format', '-f', default=log_format)
        self.opts = self.parser.parse_args(args)

        logging.basicConfig(format=self.opts.log_format, level=self.opts.log_level)

        # "quiet" flags are enabled unless DEBUG log mode.
        self.quiet = self.opts.log_level != 'DEBUG'

        # Load initial env data from configs.
        self.set_env(self.opts.env)

        if self.opts.what == 'node':
            self.cluster.node_exec(self.opts.node, self.opts.method)
        elif self.opts.what == 'app':
            if not self.opts.app in self.apps:
                raise Exception(f'No app named {self.opts.app}')
            getattr(self.apps[self.opts.app], self.opts.method)()


"""
MAIN
"""
if __name__ == "__main__":
    m8ke = M8ke()
