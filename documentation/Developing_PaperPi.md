# Developing for PaperPi

## Quick Start

1. Clone the repo: `git clone https://github.com/ysadamt/PaperPi.git`
2. From the repo root run the development init script: `./utilities/init_devel_environment.sh -h`
3. Start developing - see the notes below about [required packages](#required-debian-packages)


## Development Environment

The development init script will create a python virtual environment, prompt for required Debian package. To activate the virtual environment use `source .PaperPi/utilities/venv_activate` or alternatively `source PaperPi/paperpi_venv/bin/activate`.

PaperPi can be developed in Jupyter notebooks. Runing the init script with the `-j` option will create the venv, install the appropriate Jupyter related packages and install the Jupyter kernel. To start a Jupyter session and connect from a remote computer on the same network use the command below, then connect to the supplied URL.

Command:
```
MYHOST=$(hostname -I | cut -d " " -f 1); jupyter notebook --ip=$MYHOST --no-browser
```

Output:
```bash
pi@bookworm32t:~/PaperPi $ MYHOST=$(hostname -I | cut -d " " -f 1); jupyter notebook --ip=$MYHOST --no-browser
[I 18:53:43.302 NotebookApp] Serving notebooks from local directory: /home/pi/PaperPi
[I 18:53:43.302 NotebookApp] Jupyter Notebook 6.4.12 is running at:
[I 18:53:43.302 NotebookApp] http://192.168.1.209:8888/?token=ed2bda1679e3f2c8c8b852df3d1f44fc5937f7674404fd2a
[I 18:53:43.303 NotebookApp]  or http://127.0.0.1:8888/?token=ed2bda1679e3f2c8c8b852df3d1f44fc5937f7674404fd2a
[I 18:53:43.303 NotebookApp] Use Control-C to stop this server and shut down all kernels (twice to skip confirmation).
[C 18:53:43.323 NotebookApp]

    To access the notebook, open this file in a browser:
        file:///home/pi/.local/share/jupyter/runtime/nbserver-22902-open.html
    Or copy and paste one of these URLs:
        http://192.168.1.209:8888/?token=ed2bda1679e3f2c8c8b852df3d1f44fc5937f7674404fd2a
     or http://127.0.0.1:8888/?token=ed2bda1679e3f2c8c8b852df3d1f44fc5937f7674404fd2a
```

## Required Debian Packages

Basic development depends on the packages listeded here

- [debian_packages-paperpi](../paperpi/debian_packages-paperpi.txt)

Some plugins may have additional Debian requirements. These plugins are documented in `./paperpi/plugins/[plugin_name]/debian_packages-plugin_name..txt`

If your plugin requires additional Debian packages to function, make sure to list them as a bash style array. See the example below:

```bash
# list the packages using the full and complete package name
# NOTE that bash arrays are always in parentheses, do not use commas and there is 
# no space between the variable name and the `=` sign.
DEBPKG=( "libtiff-dev" "libopenjp2-7" "python3-pip" "python3-venv" )
```