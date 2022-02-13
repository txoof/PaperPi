#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )




function install_devel_requirements {
  # create pipenv for this project
  if [ $INSTALL -gt 0 ]
  then
    "installing all plugin development requirements"
    # find all the plugin requirements and install using pipenv install
    tempfile=$(mktemp)
    find $SCRIPT_DIR/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \;
    echo "Installing development dependencies for all plugins:"
    cat $tempfile
    pushd $SCRIPT_DIR/../  > /dev/null 2>&1
    # add all the modules from the plugins
    pipenv install --dev -r $tempfile --skip-lock
    popd > /dev/null 2>popd1
  fi
}

function clean_devel_modules {
  # clean development modules and start fresh
  if [ $INSTALL -gt 0 ] 
  then
    echo "removing all previous development modules"
    pushd $SCRIPT_DIR/../  > /dev/null 2>&1
    pipenv uninstall --all-dev --skip-lock
    popd > /dev/null 2>popd1
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
  -i)
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

clean_devel_modules
install_devel_requirements
rm_venv

