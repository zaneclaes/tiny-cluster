#!/usr/bin/env python3
import os, sys, argparse, yaml, subprocess, glob, logging, urllib.request
from urllib.parse import urlparse
from deepmerge import always_merger

class App():
    def __init__(self, m8ke, env_dir, name, env):
        self.env_dir = env_dir
        self.name = name
        self.env = env
        self.parts = [self.env_dir]
        self.m8ke = m8ke
        self.log = logging.getLogger(name)

        args = sys.argv[1:]

        if not env:
            print(f'Available environments: {list(self.environments)}')
            print(f'Available apps: {app_names}')
            print(f'Current context is: ' + self.get_context())
            exit(0)

        self.dir_app = os.path.join(self.env_dir, name)
        self.dir_env = os.path.join(self.dir_app, env)

    def _confirm(self):
        if self.m8ke.cluster.protected:
            a = input(f'{self.env} is protected. Are you sure? [y/N] ')
            if a.lower() != 'y': exit(0)

    def apply(self, confirmed = False):
        if not confirmed: self._confirm()

        if not os.path.isdir(self.dir_env):
            print(f'No kustomization directory at {self.dir_env}')
            a = input(f'Do you want to add {self.name} to {self.env}? [y/N] ')
            if a.lower() != 'y': exit(1)
            os.mkdir(self.dir_env)

        rf = os.path.join(self.dir_app, 'app.yaml')
        self.release = { 'namespace': None, 'base': 'base' }
        if os.path.isfile(rf):
            with open(rf, 'r') as stream:
                data = yaml.safe_load(stream)
                if data: self.release.update(data)

        self.namespace = self.release['namespace']

        self.layer = self._get_kustomization(self.env)

        if not 'bases' in self.layer or len(self.layer['bases']) <= 0:
            a = input(f'What is the base layer for {self.env}? [{self.release["base"]}] ')
            if len(a) <= 0: a = self.release["base"]

            self.dir_base = os.path.join(self.dir_app, a)
            if not os.path.isdir(self.dir_base): os.mkdir(self.dir_base)

            self.layer['bases'] = [f'../{a}']
            # Ensure there's a base file.
            self._set_kustomization(a, self._get_kustomization(a))

        # Ensure namespace applied to Kustomization
        if not 'commonLabels' in self.layer: self.layer['commonLabels'] = {}
        self.layer['commonLabels']['env'] = self.env
        self.layer['commonLabels']['app'] = self.name
        if self.namespace: self.layer['namespace'] = self.namespace

        self.log.debug(f'{rf}: {self.release}')

        # Download imports:
        if 'import' in self.release: self._imports(self.release['import'])

        # Compile helm & integrate resources to base layer:
        if 'helm' in self.release: self._helm(self.release['helm'])

        self._set_kustomization(self.env, self.layer)

        print(f'Applying {self.name} to {self.env}...')
        app = f'kubectl apply -k {self.dir_env}'
        r = subprocess.run(app, shell=True, check=False, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr.strip())
            exit(r.returncode)
        lines = r.stdout.strip().split('\n')

        print('------------------------------------------')
        unchanged = [l for l in lines if l.endswith(' unchanged')]
        print(f'{len(unchanged)} resources unchanged.')

        changed = [l for l in lines if not l.endswith(' unchanged')]
        if len(changed) > 0:
            print(f'Updated Resources:\n' + '\n'.join(changed))

    def recreate(self):
        self.delete()
        self.apply(True)

    def delete(self):
        self._confirm()
        app = f'kubectl delete -k {self.dir_env}'
        subprocess.run(app, shell=True, check=True, capture_output=False)

    def _imports(self, urls):
        self.dir_imports = os.path.join(self.dir_env, 'imports')
        if not os.path.isdir(self.dir_imports): os.mkdir(self.dir_imports)

        for url in urls:
            fn = os.path.basename(urlparse(url).path)
            print(f'Downloading {fn}...')
            urllib.request.urlretrieve(url, os.path.join(self.dir_imports, fn))
            self._add_resource(os.path.join('imports', fn))

    def _add_resource(self, path):
        if not 'resources' in self.layer: self.layer['resources'] = []
        if not path in self.layer['resources']: self.layer['resources'].append(path)

    def _helm(self, helm):
        self.helm = always_merger.merge({
            'values': 'values.yaml',
            'repo': 'stable',
        }, helm)

        # Merge values together
        values = {}
        vfs = [
            os.path.join(self.dir_app, self.release["base"], self.helm['values']),
            os.path.join(self.dir_app, self.env, self.helm['values'])
        ]
        for vf in vfs:
            if os.path.isfile(vf):
                with open(vf, 'r') as stream:
                    values = always_merger.merge(values, yaml.safe_load(stream))
        values_fp = None
        if len(values) > 0:
            values_fp = os.path.join(self.dir_app, f'.values-{self.env}.yaml')
            with open(values_fp, 'w+') as stream:
                yaml.dump(values, stream, default_flow_style=False)

        # Build helm chart and merge into Kustomization.
        hc = f'helm template {self.name} '
        hc += f'--output-dir {self.dir_env} '
        if (self.namespace): hc += f'--namespace {self.namespace} '
        if values_fp is not None: hc += f'--values {values_fp} '
        hc += self.helm['repo'] + '/' + self.helm['chart']

        rel_dir_templates = self.helm['chart']
        self.dir_templates = os.path.join(self.dir_env, rel_dir_templates)
        print(f'Building helm chart @{self.dir_templates}...')

        # Build the correct list of resources...
        r = subprocess.run(hc, shell=True, check=False, capture_output=True, text=True)
        if r.returncode != 0:
            raise Exception(r.stderr)
            exit(r.returncode)

        wr = r.stdout.strip().split('\n')
        prefix = f'wrote {self.dir_env}'
        for fn in wr:
            if not fn.startswith(prefix): continue
            fn = fn[len(prefix)+1:]
            # Ugly way to exclude tests from kustomization...
            if '/tests/' in fn or '/test-' in fn: continue
            self._add_resource(fn)

        if values_fp is not None: os.remove(values_fp)

    # Get the kustomization values for ./[app]/[layer]/kustomization.yaml
    def _get_kustomization(self, layer):
        fp = os.path.join(self.dir_app, layer, 'kustomization.yaml')
        data = None
        if os.path.isfile(fp):
            with open(fp, 'r') as stream: data = yaml.safe_load(stream)
        if not data: data = {}
        return data

    def _set_kustomization(self, layer, data):
        fp = os.path.join(self.dir_app, layer, 'kustomization.yaml')
        with open(fp, 'w+') as stream: yaml.dump(data, stream, default_flow_style=False)
        return data
