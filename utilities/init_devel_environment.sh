#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname $SCRIPT_DIR)

# get the currently installed python version
PY_VERSION=$(python3 -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

# virtual environment name
VENV_HASH=$(echo -n "$PROJECT_DIR" | md5sum | cut -c1-10)
VENV=$PROJECT_DIR/venv_paperpi-$VENV_HASH

# options and packages required for jupyter
# jupyter debian packages
JUPYTER_DPKG="$PROJECT_DIR/utilities/debian_packages-jupyter_devel.txt"
# jupyter python modules
JUPYTER_MODS=( "jupytext" )



function abort {
  # abort installation with message
  printf "%s\n" "$@"
  printf "%s\n\nThis installer can be resumed with:\n"
  printf "sudo $SCRIPT_DIR/$(basename "$0")\n"
  exit 1
}

function Help {
  echo "
  Create a development environment for this project

  usage:
  $ $0 [option]

  options:
  -c: create the virtual environment
  -j: create the virtual environment and add jupyter kernel
  -h: This help screen
  -p: purge the virtual environment and clean up kernel specs
  --info: virtual environment information

"
exit 0
}

# check for underlying debian packages required for development
function check_deb_system {

    CHECK_PATH="$PROJECT_DIR/paperpi"
    find "$CHECK_PATH" -name "debian_packages-*.txt" >>tmpfile
    mapfile -t array < tmpfile
    rm -f tmpfile

    if [ $INSTALL -lt 1 ]
    then
        uninstall=()
        echo "The following pakcages MAY have been installed during the environment init:"
        for i in "${array[@]}"
        do
            source "${i}"
            for i in "${DEBPKG[@]}"
            do
                echo "$i"
                uninstall+=($i)
            done            
        done

        echo "
Packages can be removed AT YOUR OWN RISK using:"
        echo "  $ apt remove ${uninstall[@]}"
        echo "
NOTE: Some of these packages may have already existed on your system or may be required by other programs. 
Remove them at your own risk!"

        return
    fi

    echo "Locating required debian system packages in $CHECK_PATH"

    halt=0
    missing=()
    # get all files that match debian_packages-*.txt
    

    if [ $JUPYTER -gt 0 ]
    then
        array+=( $JUPYTER_DPKG )
    fi

    for i in "${array[@]}"
    do
        echo "Checking debian system packages for PaperPi found in: '$(basename $i)'"
        source "${i}"
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
            else
                echo "$i OK"

            fi
        done        
    done

    if [[ $halt -gt 0 ]]
    then
        echo "$halt required packages are missing.
    install missing packages with: 
    
        $ sudo apt install ${missing[*]}
    
    stopping install"
        abort
    else    
        echo "All required debian system packages are installed"
    fi

}

# check that SPI is enabled
function check_spi {
    if [ $INSTALL -lt 1 ] 
    then
        # nothing to do here if not installing
        echo ""
    else
        echo "Checking for SPI"
        if [[ $(sudo raspi-config nonint get_spi) = "1" ]]
        then
            echo ""
            echo "SPI is not enabled and is required for PaperPi to function"
            echo "enable with:"
            echo "$ sudo raspi-config nonint do_spi 0"
            abort
        else
            echo "SPI OK"        
        fi
    fi
}

# create a virtual environment to work in
# add jupyter essentials if asked
function create_venv {
  venvName=$(basename $VENV)

  if [ $INSTALL -gt 0 ]
  then
    echo "Creating virtual environment in $VENV"
    if [ -f $VENV/bin/activate ]
    then
      echo "Virtual environment in $VENV exists"
    else
      pushd $PROJECT_DIR
      python3 -m venv $VENV
      popd
      ln -s $VENV/bin/activate $PROJECT_DIR/venv_activate
    fi

    echo "Installing development requirements"
    tempfile=$(mktemp)
    cat $PROJECT_DIR/requirements.txt > $tempfile

    cat $PROJECT_DIR/utilities/requirements-devel.txt >> $tempfile
    
    if [ $JUPYTER -gt 0 ]
    then
      cat $PROJECT_DIR/utilities/requirements-jupyter_devel.txt >> $tempfile
    fi

    find $PROJECT_DIR/paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \;
    cat $tempfile
    $VENV/bin/python -m pip install -r $tempfile

    echo "Activate the virtual environment by running:
  $ source $PROJECT_DIR/utilities/venv_activate"
  fi

  if [ $JUPYTER -gt 0 ]
  then
    echo "Installing kernel spec for $venvName"
    if ! $VENV/bin/python -m pip show "ipykernel" > /dev/null; then
      echo "Installying Jupyter ipykernel module for this virtual environment"
      $VENV/bin/pip3 install ipykernel
    fi
    echo "Adding kernel spec: $venvName"
    $VENV/bin/python -m ipykernel install --user --name "$venvName"
  fi

  if [ $PURGE -gt 0 ]
  then
    echo "Purging kernelspec $venvName"
    jupyter kernelspec remove $venvName $venvName
    rm -rf $VENV
    echo "Removing $VENV"
  fi
}

# give jupyter hints
function jupyter_hints {
    if [ $JUPYTER -gt 0 ]
    then
        echo "Hints for staring a Jupyter session:"
        MY_HOST=$(hostname -I | cut -d " " -f 1)
        echo "To launch a Jupyter development environment, run:
        $ jupyter notebook --ip=$MY_HOST --no-browser
        
        Then connect to http://$MY_HOST:8888 from a browser on the local network to get started"
    fi
}

function venv_info {
  if [ ! -d $VENV ]
  then
    echo "No virtual environment exists for this project.
Create a virtual environment with:
  $0 -c|-j

For more information:
  $0 -h
    "
    exit 0
  fi

  echo "Virtual environtment information
  * Path: $VENV
  * Activate virtual env: 
    $ source $PROJECT_DIR/utilities/venv_activate

"

  if $VENV/bin/python3 -m pip show "ipykernel" > /dev/null; then
    myHost=$(hostname -I | cut -d " " -f 1)
    echo "Jupyter Information:
  * Launch Jupyter Notebook locally: 
    $ cd ~; jupyter-notebook

  * Launch Jupyter Notebook for remote access:
    $ cd ~; jupyter notebook --ip=$myHost --no-browser

"
  fi
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


check_deb_system
check_spi
create_venv
jupyter_hints