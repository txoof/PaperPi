#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname $SCRIPT_DIR)



function install_devel_requirements {
  # create pipenv for this project
  if [ $INSTALL -gt 0 ]
  then
    echo "installing all plugin development requirements"
    # find all the plugin requirements and install using pipenv install
    tempfile=$(mktemp)
    find $PROJECT_DIR/paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \;
    echo "Installing development dependencies for all plugins:"
    cat $tempfile
    pushd $PROJECT_DIR  > /dev/null 2>&1
    # add all the modules from the plugins
    echo "tempfile: $tempfile"
    pipenv install --dev -r $tempfile --skip-lock
    popd > /dev/null 2>&1
  fi
}

function clean_devel_modules {
  # clean development modules and start fresh
  if [ $INSTALL -gt 0 ] 
  then
    echo "removing all previous development modules"
    pushd $PROJECT_DIR/../  > /dev/null 2>&1
    pipenv uninstall --all-dev --skip-lock
    popd > /dev/null 2>&1
  fi
}

function rm_venv {
  # completely remove pipenv
  if [ $PURGE -gt 0 ]
  then
    echo "removing pipenv virtual environment"
    pushd $SCRIPT_DIR/../  > /dev/null 2>&1
    pipenv --rm
    popd > /dev/null 2>popd1
  fi
}

function Help {
  echo "
  Create a development environment for this project

  usage:
  $ $0 option

  options:
  -c: create the virtual environment
  -h: This help screen
  -p: purge the virtual environment
  --info: virtual environment information

"
exit 0
}

function venv_info {
  echo "Pipenv Information:"
  pushd $SCRIPT_DIR/../ > /dev/null 2>&1
  pipenv graph
  pipenv --venv
  exit 0
}


## main program ##
INSTALL=0
PURGE=0


while [[ $# -gt 0 ]]; do
  case $1 in
  -h)
    Help
    exit
    shift
    shift
    ;;
  -c)
    INSTALL=1
    PURGE=0
    shift
    shift
    ;;
  -p)
    PURGE=1
    INSTALL=0
    shift
    shift
    ;;

  --info)
    venv_info
    exit 0
    ;;
  -*)
    echo "unknown option: $1"
    echo ""
    Help
    exit
    ;;
  *)
    shift
    ;;
  esac
done

if [[ $INSTALL -eq 0 ]] && [[ $PURGE -eq 0 ]]; then
  Help
fi

if ! command pip3 > /dev/null 2>&1
then
  echo "pip3 is not installed and is required for this development enviornment"
  echo "try:
  sudo apt install python3-pip
  "
  exit
fi

if ! command pipenv > /dev/null 2>&1
then
  echo "pipenv is not installed and is required for this development environemnt"
  echo "try:
  pip3 install pipenv

for a system-wide install try:
  sudo pip3 install pipenv
  "
  exit 1
fi

clean_devel_modules
install_devel_requirements
rm_venv

