# from distutils.core import setup
from setuptools import setup

__version__ = '0.1'

setup(name = 'nose-traggr',
      packages = ['.'],
      version = __version__,
      description = 'Nose plugin for posting results into Test Results Aggregation system',
      author = 'Vitaliy Yakoviv',
      author_email = 'witalick@gmail.com',
      url = 'https://github.com/witalick/nose-traggr',
      keywords = ['nose', 'plugin', 'testing', 'reporting'],
      classifiers = [],
      entry_points = {
        'nose.plugins.0.10': [
            'traggr = traggr:TRAggr'
        ]
      },
      install_requires=['traggr-api-client', 'nose'])

