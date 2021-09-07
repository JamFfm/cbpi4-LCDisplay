from setuptools import setup, find_packages

# read the contents of your README file
from os import path

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(name='cbpi4-LCDisplay',
      version='5.0.8',
      description='CraftBeerPi4 LCD Plugin',
      author='Jan Battermann',
      author_email='jan.battermann@t-online.de',
      url='https://github.com/JamFfm/cbpi4-LCDisplay',
      license='GPLv3',
      packages=find_packages(),
      include_package_data=True,
      package_data={
          # If any package contains *.txt or *.rst files, include them:
          '': ['*.txt', '*.rst', '*.yaml'],
          'cbpi4-LCDisplay': ['*', '*.txt', '*.rst', '*.yaml']},
      # packages=['cbpi4-LCDisplay'],
      install_requires=[
          'cbpi>=4.0.0.33',
          'smbus2',
      ],
      long_description=long_description,
      long_description_content_type='text/markdown'
      )
