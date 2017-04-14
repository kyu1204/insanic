import os
import sys
import types

import ujson as json

from sanic.config import Config

from . import global_settings

class DockerSecretsConfig(Config):

    def __init__(self, defaults=None):
        super().__init__(defaults)
        self.from_object(global_settings)
        self._load_secrets()

    def _load_secrets(self):
        try:
            with open('/run/secrets/{0}'.format(os.environ['MMT_SERVICE'])) as f:
                docker_secrets = json.load(f)
            for k, v in docker_secrets:
                self.update({k: v})
        except FileNotFoundError as e:
            sys.stderr.write("File not found %s" % e.strerror)
            filename = os.path.join(os.getcwd(), 'instance.py')
            module = types.ModuleType('config')
            module.__file__ = filename

            try:
                with open(filename) as f:
                    exec(compile(f.read(), filename, 'exec'),
                         module.__dict__)
            except IOError as e:
                sys.stderr.write('Unable to load configuration file (%s)' % e.strerror)
            for key in dir(module):
                if key.isupper():
                    self[key] = getattr(module, key)

settings = DockerSecretsConfig()




