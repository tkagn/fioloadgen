import os
import sys

from configparser import ConfigParser, ParsingError

# create a settings object

global settings


def init(mode='dev'):
    global settings

    settings = Config(mode)


class Config(object):

    _config_dir_list = {
        "prod": [
            "/etc/fioloadgen/fioservice.ini",
            os.path.join(os.path.expanduser('~'), 'fioservice.ini'),
        ],
        "dev": [
            os.path.join(os.path.expanduser('~'), 'fioservice.ini'),
        ]
    }

    _global_defaults = {
        "prod": {
            "db_name": "fioservice.db",
            "db_dir": "/var/lib/fioloadgen",
            "job_dir": "/var/lib/fioloadgen/jobs",
            "log_dir": "/var/log/fioloadgen",
            "ssl": True,
            "ip_address": "0.0.0.0",
            "port": 8080,
            "debug": False,
        },
        "dev": {
            "db_name": "fioservice.db",
            "db_dir": os.path.expanduser('~'),
            "job_dir": os.path.join(os.getcwd(), "data", "fio", "jobs"),
            "log_dir": os.path.expanduser('~'),
            "ssl": True,
            "ip_address": "0.0.0.0",
            "port": 8080,
            "debug": False,
        }
    }

    _client_defaults = {}

    def __init__(self, mode='dev'):
        # establish defaults based on the mode
        self.run_mode = mode
        self.db_name = Config._global_defaults[mode].get('db_name')
        self.db_dir = Config._global_defaults[mode].get('db_dir')
        self.log_dir = Config._global_defaults[mode].get('db_dir')
        self.ssl = Config._global_defaults[mode].get('ssl')
        self.port = Config._global_defaults[mode].get('port')
        self.debug = Config._global_defaults[mode].get('debug')
        self.job_dir = Config._global_defaults[mode].get('job_dir')
        self.ip_address = Config._global_defaults[mode].get('ip_address')

        self._apply_overrides()

    @property
    def dbpath(self):
        return os.path.join(self.db_dir, 'fioservice.db')

    def _apply_overrides(self):

        def converted_value(value):
            bool_types = {
                "TRUE": True,
                "FALSE": False,
            }

            if value.isdigit():
                value = int(value)
            elif value.upper() in bool_types:
                value = bool_types[value.upper()]

            return value

        # define a list of valid vars
        valid_sections = ['global']
        global_vars = set()
        global_vars.update(Config._global_defaults['prod'].keys())
        global_vars.update(Config._global_defaults['dev'].keys())

        # Parse the any config files that are accessible
        parser = ConfigParser()
        try:
            config = parser.read(Config._config_dir_list[self.run_mode])
        except ParsingError:
            print("invalid ini file format, unable to parse")
            sys.exit(12)

        if config:
            sections = parser.sections()
            if not sections or not all(s in valid_sections for s in sections):
                print("config file has missing/unsupported sections")
                print("valid sections are: {}".format(','.join(valid_sections)))
                sys.exit(12)

            # Apply the overrides
            for section_name in sections:
                if section_name == 'global':
                    for name, value in parser.items(section_name):
                        if name in global_vars:
                            print("[CONFIG] applying override: {}={}".format(name, value))
                            setattr(self, name, converted_value(value))
                        else:
                            print("-> {} is unsupported, ignoring")
        else:
            print("no configuration overrides, using defaults")
