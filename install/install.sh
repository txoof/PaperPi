#!/usr/bin/env bash

trap '{ echo "Ctrl-C detected. Quitting." ; abort; }' INT

SOURCE=${BASH_SOURCE[0]}
while [ -h "$SOURCE" ]; do # resolve $SOURCE until the file is no longer a symlink
  DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )
  SOURCE=$(readlink "$SOURCE")
  [[ $SOURCE != /* ]] && SOURCE=$DIR/$SOURCE # if $SOURCE was a relative symlink, we need to resolve it relative to the path where >
done
SCRIPT_DIR=$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )


APPNAME="paperpi"
LOCALPATH="$SCRIPT_DIR/../paperpi"
INSTALLPATH="/usr/local/"
BINPATH="/usr/local/bin/"
CWD=$(pwd)

# files to include/exclude when installing
INCLUDE="$SCRIPT_DIR/install_include.txt"
EXCLUDE="$SCRIPT_DIR/install_exclude.txt"


SYSTEMD_UNIT_FILE_NAME="$APPNAME-daemon.service"
SYSTEMD_UNIT_PATH="/etc/systemd/system/$SYSTEMD_UNIT_FILE_NAME"

CONFIG_FILE_NAME=$APPNAME.ini
SYSTEM_CONFIG_PATH=/etc/default/$CONFIG_FILE_NAME

function abort {
  # abort installation with message
  printf "%s\n" "$@"
  printf "%s\n\nThis installer can be resumed with:\n"
  printf "sudo $SCRIPT_DIR/$(basename "$0")\n"
  exit 1
}


# install requirements from the plugin requirements-*.txt files
function install_plugin_requirements {

  if [ $INSTALL -gt 0 ]
  then
    echo "Installing requirements in virtual environment for $APPNAME plugins"
    pushd $INSTALLPATH/$APPNAME
    # find all the plugin requirements and install using pipenv install 
    tempfile=$(mktemp)
    find $SCRIPT_DIR/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \; 
    echo "installing Plugin requirements:"
    cat $tempfile
    if ! command pipenv install -r $tempfile --skip-lock
    then
      popd
      abort "failed to install python modules" 
    fi
    popd
  else
    echo ""
  fi

}

function copy_files {

  if [ $INSTALL -ge 1 ]
  then
    echo "Installing files to $INSTALLPATH"
    rsync -a --exclude-from=$EXCLUDE --include-from=$INCLUDE $LOCALPATH $INSTALLPATH
    cp $SCRIPT_DIR/../Pipfile $INSTALLPATH/$APPNAME
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then
    echo "Removing files from $INSTALLPATH/$APPNAME"
    rm -rf $INSTALLPATH/$APPNAME
  fi

}

# create the pipenv for the install using the local python3 interpreter
function create_pipenv {

  if [ $INSTALL -gt 0 ]
  then
    echo "Creating virtual environment for $APPNAME in $INSTALLPATH"
    pushd $INSTALLPATH/$APPNAME
    if ! command pipenv install --skip-lock
    then
      popd
      abort "failed to install python modules"
    fi
    popd
  else
    echo ""
  fi

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

function check_py_packages {
  halt=0
  missing=()

  if [ $INSTALL -lt 1 ]
  then
    # nothing to do here for purge or uninstall
    echo ""
  else
    echo "checking python environment"
    echo ""
    source $SCRIPT_DIR/required_python_packages.txt
    for i in "${REQUIRED_PY[@]}"
    do
      echo "verifying python package $i"
      if ! pip3 show $i > /dev/null 2>&1
      then
        echo ""
        echo "missing $i, attempting to install"
        echo ""
        pip3 install $i 
        if pip3 show $i > /dev/null 2>&1
        then
          echo ""
          echo "missing $i installed successfully. continuing..."
          echo ""
        else
          echo ""
          echo "automatic install of $i failed. Manual installation may be required"
          echo ""
          halt=$((halt+1))
          missing+=( $i )
        fi
      else
        echo "...OK"
      fi
    done
  fi

  if [[ $halt -gt 0 ]]
  then
    echo "$halt required python packages are missing. See messages above."
    echo "install missing packages with:"
    echo "sudo pip3 install ${missing[*]}"
    echo ""
    echo "stopping install"
    abort
  fi
}

function install_executable {
  if [ $INSTALL -gt 0 ]
  then
    echo "adding executable to $BINPATH/paperpi"
    cp $SCRIPT_DIR/paperpi $BINPATH
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ] 
  then
    echo "removing excutable at $BINPATH/paperpi"
    rm $BINPATH/paperpi
  fi
}

function add_user {
  if [ $INSTALL -gt 0 ]
  then
    echo "adding user and group $APPNAME"
    /usr/sbin/useradd --system $APPNAME
    result=$?
    if [ $result -ne 0 ] && [ $result -ne 9 ]
    then
      echo "failed to add user"
      echo "install aborted"
      abort
    fi

    /usr/sbin/usermod -a -G spi,gpio $APPNAME
    if [ $? -ne 0 ]
    then
      echo "failed to add user to groups: spi, gpio"
      echo "install aborted"
      abort
    fi
  fi

  if [ $PURGE -gt 0 ]
  then
    echo "removing user and group: $APPNAME"
    /usr/sbin/usermod -G $APPNAME $APPNAME
    if [ $? -ne 0 ]
    then
      echo faile to delete user $APPNAME
      ERRORS=$((ERRORS+1))
    fi
  fi
}


function install_unit_file {
  if [ $INSTALL -eq 1 ]
  then
    DAEMON_INSTALL = 1
    echo "installing systemd unit file to: $SYSTEMD_UNIT_PATH"
    cp $SCRIPT_DIR/$SYSTEMD_UNIT_FILE_NAME $SYSTEMD_UNIT_PATH
    if [ $? -ne 0 ]
    then
      echo "failed to copy unit file"
      echo "exiting"
      abort
    fi

    echo "reloading systemd unit files"
    /bin/systemctl daemon-reload
    if [ $? -ne 0 ]
    then
      echo "failed to reload systemd untit files"
      echo "exiting"
      abort
    fi
    read -p "Would you like to enable $APPNAME to run in daemon mode? (Y/n): " edit_config
    if [[ $edit_config =~ ^([yY][eE][sS]|[yY]*)$ ]]
    then
      echo "enabling systemd unit file"
      /bin/systemctl enable $SYSTEMD_UNIT_PATH
      if [ $? -ne 0 ]
      then
        echo "failed to enable systemd untit files"
        echo "exiting"
        abort
      fi
    else
      DAEMON_INSTALL = 0
      echo ""
      echo "you selected to run on demand"
      echo "you can enable the daemon later by typing:"
      echo "sudo systemctl enable $SYSTEMMD_UNIT_PATH"
      echo ""
    fi
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then
    echo "stopping daemon"
    /usr/bin/systemctl stop $SYSTEMD_UNIT_FILE_NAME
    if [ $? -ne 0 ]
    then
      echo "failed to stop daemon"
      echo "try to stop manually with:"
      echo "$ sudo systemctl stop $SYSTEMD_UNIT_FILE_NAME"
      echo "exiting"
      abort
    fi
    
    echo "removing $SYSTEMD_UNIT_PATH"

    rm $SYSTEMD_UNIT_PATH
    if [ $? -ne 0 ]
    then
      echo "failed to remove unit file: $SYSTEMD_UNIT_PATH"
      echo "try to manually remove with:"
      echo "$ sudo rm $SYSTEMD_UNIT_PATH"
      ERRORS=$((ERRORS+1))
    fi

    echo "reloading systemd unit files"
    /bin/systemctl daemon-reload
  fi
}

function install_config {
  if [ $INSTALL -gt 0 ] 
  then
    echo "installing system config"
    INSTALL_CONFIG=0

    if [[ -f $SYSTEM_CONFIG_PATH ]]
    then
      echo "##############################################################"
      echo "existing config files found at $SYSTEM_CONFIG_PATH"
      echo "existing files will not be overwritten"
      echo ""
      echo "a new version will be added at $SYSTEM_CONFIG_PATH.new"
      echo "it may be useful to review the differences between the config files"
      echo "##############################################################"
      cp $SCRIPT_DIR/$CONFIG_FILE_NAME $SYSTEM_CONFIG_PATH.new
   
    else
      echo "adding config file: $SYSTEM_CONFIG_PATH"
      cp $SCRIPT_DIR/$CONFIG_FILE_NAME $SYSTEM_CONFIG_PATH
    fi
  fi

  if [ $PURGE -gt 0 ]
  then
    echo "removing $SYSTEM_CONFIG_PATH"
    if [ -f $SYSTEM_CONFIG_PATH ]
    then
      rm $SYSTEM_CONFIG_PATH
      if [ $? -ne 0 ]
      then
        echo "failed to remove config file"
        ERRORS=$((ERRORS+1))
      fi
    else
      echo "nothing to remove"
    fi
  fi
}


function enable_spi {
  if [ $INSTALL -gt 0 ]
  then
    echo ""
    echo "checking if SPI is enabled"
    echo ""
    if [[ $(sudo raspi-config nonint get_spi) = "1" ]]
    then 
      echo ""
      echo "SPI is not enabled, enabling now"
      echo ""
      sudo raspi-config nonint do_spi 0
    fi
  fi
}


function edit_config {
  if [ $INSTALL -gt 0 ]
  then
    CONFIG_EDITED=0
    echo "
    You must now complete the following steps
    REQUIRED:
    * edit $SYSTEM_CONFIG_PATH and set:
      - display_type = [YOUR_SCREEN]
      - vcom = [only set for HD screens]

    OPTIONAL:
    * Enable plugins by removing the \"x\" from section headers
    * Configure the plugins to match your needs/environment
    "
    read -p "Would you like to do that now? (y/N): " edit_config
    if [[ $edit_config =~ ^[Yy]$ ]]
    then
      sudo nano $SYSTEM_CONFIG_PATH
      CONFIG_EDITED=1
    fi
  fi
}


function finish_install()
{
  if [ $INSTALL -gt 0 ]
  then
    echo ""
    echo "install completed"
    echo ""
    if [ $CONFIG_EDITED -lt 1 ]
    then
    echo "
      Before running the programs you must complete the following steps
      REQUIRED:
      * edit $SYSTEM_CONFIG_PATH and set:
        - display_type = [YOUR_SCREEN]
        - vcom = [only set for HD screens]

      OPTIONAL:
      * Enable plugins by removing the \"x\" from section headers
      * Configure the plugins to match your needs/environment
      "
      if [ $DAEMON_INSTALL -gt 1 ]
      then
        echo ""
        echo "When completed, run the following command or reboot to start"
        echo "the $APPNAME daemon will start automatcially"
        echo ""
        echo "$ sudo systemctl start $SYSTEMD_UNIT_FILE_NAME"
      else
        echo ""
        echo "to manually start $APPNAME please run"
        echo "$ $BINPATH$APPNAME"
      fi
    fi
  fi
  

  # uninstall
  if [ $UNINSTALL -gt 0 ]
  then
    echo "uninstall completed"
  fi

  if [ $ERRORS -gt 0 ]
  then
    echo "$ERRORS errors occured, please see output above for details"
  fi
}

  

function start_service {
  if [[ $INSTALL -gt 0 && $CONFIG_EDITED -gt 0 ]]
  then
    sudo systemctl start $SYSTEMD_UNIT_FILE_NAME
  fi
}


function check_permissions {
  if [ "$EUID" -ne 0 ]
  then
    echo "

  Try:
    $ sudo $0

  This installer will setup/uninstall $APPNAME to run at system boot and does the following:
  * copy $APPNAME excutable to $BINPATH
  * create configuration files in $SYSTEM_CONFIG_PATH
  * setup systemd unit files in $SYSTEMD_UNIT_FILE_NAME
  * add user "$APPNAME" to the GPIO and SPI access groups

  To uninstall or purge all files use:
  $ $0 -u|-p
"
  exit 0
  fi
}



function Help {
  echo "
  Install/Uninstall $APPNAME to run at boot

  This installer will install $APPNAME as a daemon service to
  run at system startup.

  This installer must be run as root.

  options:
  -h        This help screen
  -u        uninstall $APPNAME
  -p        uninstall $APPNAME and purge all config files
  "

}

## main program ##
INSTALL=1
UNINSTALL=0
PURGE=0

while [[ $# -gt 0 ]]; do
  echo "processing $1"
  case $1 in
  -h) # display help
    Help
    exit
    shift
    shift
    ;;
  -u) # uninstall
    INSTALL=0
    UNINSTALL=1
    shift
    shift
    ;;
  -p) # uninstall and purge config files
    INSTALL=0
    UNINSTALL=1
    PURGE=1
    shift
    shift
    ;;
  -*) # invalid option
    echo "error: unknown option: ${1}"
    echo "" 
    Help
    exit;;
   *)
    shift
    ;;
  esac
done

ERRORS=0

if [ $PURGE -gt 0 ]
then
  echo "WARNING all $APPNAME files will be removed including config files!"
  echo "Proceed?"
  read -p "n/Y " -n 1 -r
  echo ""

  if [[ $REPLY =~ ^[Yy]$ ]]
  then
    PURGE=1
  else
    PURGE=0
    echo "exiting..."
    exit 0
  fi
fi

# set the pipenv venv to be within the project directory (1)
export PIPENV_VENV_IN_PROJECT=1

check_permissions
check_py_packages
check_deb_packages
copy_files
create_pipenv
install_plugin_requirements
install_executable
add_user
install_config
install_unit_file
enable_spi
edit_config
finish_install
start_service
