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
INSTALLPATH="/usr/local/$APPNAME"
BINPATH="/usr/local/bin/"
CWD=$(pwd)

# files to include/exclude when installing
INCLUDE="$SCRIPT_DIR/install_include.txt"
EXCLUDE="$SCRIPT_DIR/install_exclude.txt"


SYSTEMD_UNIT_FILE_NAME="$APPNAME-daemon.service"
SYSTEMD_UNIT_PATH="/etc/systemd/system/$SYSTEMD_UNIT_FILE_NAME"

CONFIG_FILE_NAME=$APPNAME.ini
SYSTEM_CONFIG_PATH=/etc/default/$CONFIG_FILE_NAME

PY_VERSION=$(python3 -c 'import sys; print("{}.{}".format(sys.version_info.major, sys.version_info.minor))')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ $PY_MINOR -gt 10 ]
then
  PY_311_OPTS="--user --break-system-packages"
else
    PY_311_OPTS="--user"
fi


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

function abort {
  # abort installation with message
  printf "%s\n" "$@"
  printf "%s\n\nThis installer can be resumed with:\n"
  printf "sudo $SCRIPT_DIR/$(basename "$0")\n"
  exit 1
}

function stop_daemon {
    echo "checking if $SYSTEMD_UNIT_FILE_NAME is running"

    if /usr/bin/systemctl is-active --quiet $SYSTEMD_UNIT_FILE_NAME
    then

      echo "stopping PaperPi daemon"
      /usr/bin/systemctl stop $SYSTEMD_UNIT_FILE_NAME
      if [ $? -ne 0 ]
      then
        echo "failed to stop daemon"
        echo "try to stop manually with:"
        echo "$ sudo systemctl stop $SYSTEMD_UNIT_FILE_NAME"
        echo "exiting"
        abort
      fi
    else  
      echo "$SYSTEMD_UNIT_FILE_NAME not running"
    fi
    echo "done"
}

function check_os {
    if [ "$SKIP_OS_CHECK" -eq 1 ]
    then
        echo "skiping OS version checking. YOU'RE ON YOUR OWN!"
        return 0
    fi

    echo "Checking OS"

    long_bit=$(getconf LONG_BIT)
    if [ ! "$long_bit" -eq 32 ]
    then 
        abort "PaperPi is supported only on 32 bit versions of RaspberryPi OS. Your version: $long_bit bit. Check README for manual install instructions"
    fi
    echo "OS OK"
}

function check_permissions {
    echo "Checking permisisons"
    if [ "$EUID" -ne 0 ]
    then
        echo "
    This installer requires root permissions and will setup/uninstall 
    $APPNAME to run at system boot. The installer does the following:

    * copy $APPNAME excutable to $BINPATH
    * create configuration files in $SYSTEM_CONFIG_PATH
    * setup systemd unit files in $SYSTEMD_UNIT_FILE_NAME
    * add user "$APPNAME" to the GPIO and SPI access groups

    Try:
    $ sudo $0

    To uninstall or purge all files use:
    $ $0 -u|-p
        "
        abort
    fi
    echo "Permissions OK"
}

function check_deb_packages {

    if [ $INSTALL -lt 1 ]
    then
        # nothing to do here if not installing
        echo ""
    else
        echo "Checking for required debian packages"
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
        echo "Required packages OK"
        fi
    fi

}

function create_user {
    if [ $INSTALL -gt 0 ]
    then
        echo "Creating user: paperpi"
        if id "paperpi" &>/dev/null; 
        then
            echo "Paperpi user alreay exists"
        else
            useradd -m paperpi
            echo "Created user 'paperpi'"
        fi
        echo "Adding paperpi to the gpio and spi groups"
        usermod paperpi -a -G spi,gpio
    fi

    if [ $PURGE -gt 0 ]
    then
        echo "Purging paperpi user"
        userdel -r paperpi
    fi
}



function copy_files {

  rsyncPath=$(dirname $INSTALLPATH)
  if [ $INSTALL -ge 1 ]
  then

  # check if existing paperpi is installed
  if [[ -d $INSTALLPATH ]] 
  then
    echo "Removing existing installation found at $INSTALLPATH"
    rm -rf $INSTALLPATH
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then
    echo "Removing files from $INSTALLPATH"
    rm -rf $INSTALLPATH
  fi

    echo "Installing files to $INSTALLPATH"
    rsync -a --exclude-from=$EXCLUDE --include-from=$INCLUDE $LOCALPATH $rsyncPath
    # cp $SCRIPT_DIR/../Pipfile $INSTALLPATH
    # chown -R paperpi:paperpi $INSTALLPATH
  fi
}


function create_venv {
  venvPath="$INSTALLPATH/venv_$APPNAME"
  if [ $INSTALL -gt 0 ]
  then
    echo "Creating virtual environment in $venvPath"
    # pushd $INSTALLPATH$APPNAME
    python3 -m venv $venvPath


    tempfile=$(mktemp)
    # find all the requirements files
    cat $SCRIPT_DIR/../requirements.txt > $tempfile
    find $SCRIPT_DIR/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \;
    echo "Installing requirements from $tempfile"
    cat $tempfile
    $venvPath/bin/python -m pip install -r $tempfile
  fi
}

function install_executable {
  if [ $INSTALL -gt 0 ]
  then
    echo "Adding executable to ${BINPATH}paperpi"
    cp $SCRIPT_DIR/paperpi $BINPATH  
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then
    rm $BINPATH/paperpi
  fi
}


function install_config {
  if [ $INSTALL -gt 0 ]
  then
    echo "Installing system config"
    INSTALL_CONFIG=0

    if [[ -f $SYSTEM_CONFIG_PATH ]]
    then
      echo "##########################################
An existing config file found at $SYSTEM_CONFIG_PATH
Existing configuration files will not be overwritten

A new version will be added at $SYSTEM_CONFIG_PATH.new
It may be useful to review the differences between the config files
Try:
  $ diff $SYSTEM_CONFIG_PATH $SYSTEM_CONFIG_PATH.new
"
    else
      cp $SCRIPT_DIR/$CONFIG_FILE_NAME $SYSTEM_CONFIG_PATH
    fi
  fi

  if [ $PURGE -gt 0 ]
  then
    echo "Purging $SYSTEM_CONFIG_PATH"
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

function install_unit_file {
  if [ $INSTALL -eq 1 ]
  then
    DAEMON_INSTALL=1
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
      DAEMON_INSTALL=0
      echo ""
      echo "you selected to run on demand"
      echo "you can enable the daemon later by typing:"
      echo "$ sudo systemctl enable $SYSTEMD_UNIT_FILE_NAME"
      echo ""
    fi
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then

    stop_daemon
    # echo "stopping daemon"
    # /usr/bin/systemctl stop $SYSTEMD_UNIT_FILE_NAME
    # if [ $? -ne 0 ]
    # then
    #   echo "failed to stop daemon"
    #   echo "try to stop manually with:"
    #   echo "$ sudo systemctl stop $SYSTEMD_UNIT_FILE_NAME"
    #   echo "exiting"
    #   abort
    # fi
    
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
        echo "When you are satisfied with your configuration, run the following command or reboot."
        echo "On boot, the $APPNAME daemon will start automatcially."
        echo ""
        echo "$ sudo systemctl start $SYSTEMD_UNIT_FILE_NAME"
        echo ""
        echo "to manually start $APPNAME run:"
        echo "$ $BINPATH$APPNAME"
      fi
    fi
  fi
  

  # uninstall
  if [ $UNINSTALL -gt 0 ]
  then
    echo "uninstall completed"
  fi
}

  

function start_service {
  if [[ $INSTALL -gt 0 && $CONFIG_EDITED -gt 0 ]]
  then
    sudo systemctl start $SYSTEMD_UNIT_FILE_NAME
  fi
}


## main program ##
INSTALL=1
UNINSTALL=0
PURGE=0
SKIP_OS_CHECK=0

while [[ $# -gt 0 ]]; do
  echo "processing $1"
  case $1 in
  -h) # display help
    Help
    exit
    shift
    shift
    ;;
  # -s) # skip OS version check
  #   SKIP_OS_CHECK=1
  #   shift
  #   shift
  #   ;;
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

#check_os
stop_daemon
check_permissions
check_deb_packages
create_user
copy_files
create_venv
install_executable
install_config
install_unit_file
enable_spi
edit_config
finish_install
start_service
