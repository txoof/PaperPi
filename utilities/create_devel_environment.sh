#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname $SCRIPT_DIR)
PYVERSION="python 3"

function abort {
  # abort installation with message
  printf "%s\n" "$@"
  printf "%s\n\nThis installer can be resumed with:\n"
  printf "sudo $SCRIPT_DIR/$(basename "$0")\n"
  exit 1
}

function check_deb_packages {

  if [ $INSTALL -lt 1 ]
  then
    # nothing to do here if not installing
    echo ""
  else
    echo "checking for required debian packages"
    halt=0

    missing=()

    # get all the debian_packages-*.txt
    array=()
    find $LOCALPATH -name "debian_packages-*.txt" -print0 >tmpfile
    while IFS=  read -r -d $'\0'; do
        array+=("$REPLY")
    done <tmpfile
    rm -f tmpfile

    # source all the DEBPKG variables
    PKGS=()
    PKGS+=(${CORE_DEB[@]})

    for i in "${array[@]}"
    do
        echo "found debian packages for PaperPi module $(basename $i)"
        source "$i"
        for i in "${DEBPKG[@]}"
        do
          echo "checking $i"
          if [ $(dpkg-query -W -f='${Status}' $i | grep -c "ok installed") -eq 0 ]
          then
            echo ""
            echo "missing $i"
            echo ""
            halt=$((halt+1))
            missing+=( $i )
          fi
        done
    done

    if [[ $halt -gt 0 ]]
    then
      echo "$halt required packages are missing."
      echo "install missing packages with: "
      echo "sudo apt install ${missing[*]}"
      echo ""
      echo "stopping install"

      abort
    else
      echo "required packages installed"
    fi
  fi

}



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

function add_kernel() {
  if [ $JUPYTER -gt 0 ]
  then
    venvDir=$(pipenv --venv)
    projectName=$(basename $venvDir)
    echo "adding kernel spec: $projectName"
    pipenv run python -m ipykernel install --user --name="${projectName}"
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
    popd > /dev/null 2>&1
  fi
}

function clean_kernel() {
  if [ $PURGE -gt 0 ]
  then
    venvDir=$(pipenv --venv)
    venvName=$(basename $venvDir| tr '[:upper:]' '[:lower:]')
    jupyter kernelspec remove $venvName $venvName
  fi
}

function Help {
  echo "
  Create a development environment for this project

  usage:
  $ $0 option

  options:
  -c: create the virtual environment
  -j: create the virtual environment and add jupyter kernel
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
JUPYTER=0


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
  -j)
    INSTALL=1
    PURGE=0
    JUPYTER=1
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

check_deb_packages
clean_devel_modules
install_devel_requirements
add_kernel
clean_kernel
rm_venv

