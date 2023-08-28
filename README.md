# export_svg

Blender's AddOn designed to export ViewPort to SVG file.

## Origin

- Author: [Liero](https://blenderartists.org/u/liero/summary)
- Topic: [blenderartists.org](https://blenderartists.org/t/svg-output-script/566412)
- First version of script:  Feb 2013.

## Installation

1. Select the most fitting `export_svg_*.py` file to your version of Blender 3D
2. Follow regular instruction from [Blender Manuals](https://www.cgchan.com/static/doc/sceneskies/1.1/installation.html#installing)

## Contribution

You are free to propose changes as a PR.

### How to?

- requirements.txt contains required packages for development under Blender3.3; in addition other packages required for development
- Consider usage of virtual environment

### Preparation of environment

1. Install Python 3.7 with `pip` module
2. Upgrade pip: `python -m pip install --upgrade pip`
3. (Optional) Prepare virtual environment
   1. Install `virtualenv`
   2. Create virtual environment: `python -m venv venv`
   3. Activate virtual environment: e.g. `./venv/Scripts/activate`
4. Install packages: `pip install -r requirements.txt`

### Running test

1. Follow [Preparation of environment](#preparation-of-environment)
2. Run `pytest`

### Development

1. (Optional) Open IDE of your choice.
2. Open Blender 3.3.
3. Open Scripting perspective in Blender.
4. Load developed plugin to script editor.
5. If script is executed outside of Blender's script editor reload script.
6. Each time when you change script you need to execute it.
7. Play with plugin in Blender and provide changes to script. Repeat from point 4.

## You found an issue?

Rise a ticket with label `bug`. Better description of problem increase chance to solve an issue.

Contributors will try to solve issue but remember. It will be fixed in free time manner - be patient. Nobody pay us. ;)

## You have proposals?

Rise a ticket with label `feature_proposal` proposal. It will be discussed if Contributors are able to implement such feature regarding to available resources.

## Release notes

### v0.0.1

- original version of script for Blender 2.80
