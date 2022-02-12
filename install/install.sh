#!/usr/bin/env bash

APPNAME="paperpi"
LOCALPATH="../paperpi"
INSTALLPATH="/usr/local/"
BINPATH="/usr/local/bin/"
CWD=$(pwd)

# files to include/exclude when installing
INCLUDE="./install_include.txt"
EXCLUDE="./install_exclude.txt"


SYSTEMD_UNIT_FILE_NAME="$APPNAME-daemon.service"
SYSTEMD_UNIT_="/etc/systemd/system/$SYSTEMD_UNIT_FILE_NAME"

# set the pipenv venv to be within the project directory (1)
export PIPENV_VENV_IN_PROJECT=1


function stop_daemon {
  echo ""
}


# install requirements from the plugin requirements-*.txt files
function install_plugin_requirements {

  if [ $INSTALL -gt 0 ]
  then
    pushd $INSTALLPATH/$APPNAME
    # find all the plugin requirements and install using pipenv install 
    tempfile=$(mktemp)
    find $CWD/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \; 
    echo "installing Plugin requirements:"
    cat $tempfile
    pipenv install -r $tempfile --skip-lock
  else
    echo ""
  fi

}

function copy_files {

  if [ $INSTALL -ge 1 ]
  then
    echo "Installing files to $INSTALLPATH"
    rsync -a --exclude-from=$EXCLUDE --include-from=$INCLUDE $LOCALPATH $INSTALLPATH
    cp ../Pipfile $INSTALLPATH/$APPNAME
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
    pushd $INSTALLPATH/$APPNAME
    pipenv install --skip-lock
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
    echo "checking for required packages"
    halt=0

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
        echo "found packages for module $(basename $i)"
        source "$i"
        for i in "${DEBPKG[@]}"
        do
          echo "checking $i"
          if [ $(dpkg-query -W -f='${Status}' $i | grep -c "ok installed") -eq 0 ]
          then
            echo "Required debian package $i not installed. Install with:"
            echo "sudo apt install $i"
            echo ""
            halt=$((halt+1))
          fi

        done

    done

    if [[ $halt -gt 0 ]]
    then
      echo "$halt required packages are missing."
      echo "stopping install"
      exit 1
    else
      echo "required packages installed"
    fi
  fi

}

function check_py_packages {
  halt=0

  if [ $INSTALL -lt 1 ]
  then
    # nothing to do here for purge or uninstall
    echo ""
  else
    echo "checking python environment"
    echo ""
    source python_packages.txt
    for i in "${REQUIRED_PY[@]}"
    do
      echo "verifying python package $i"
      if ! pip show $i > /dev/null 2>&1
      then
        echo "required python package $i not installed. Install with:"
        echo "pip3 install $i"
        echo ""
        halt=$((halt+1))
      else
        echo "...OK"
      fi
    done
  fi

  if [[ $halt -gt 0 ]]
  then
    echo "$halt required pytyhon packages are missing. See messages above."
    echo "stopping install"
    exit 1
  fi
}

function install_executable {
  if [ $INSTALL -gt 0 ]
  then
    echo "adding executable to $BINPATH/paperpi"
    cp paperpi $BINPATH
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
      exit 1
    fi

    /usr/sbin/usermod -a -G spi,gpio $APPNAME
    if [ $? -ne 0 ]
    then
      echo "failed to add user to groups: spi, gpio"
      echo "install aborted"
      exit 1
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
    echo "installing systemd unit file to: $SYSTEMD_UNIT_PATH"
    cp $SYSTEMD_UNIT_FILE $SYSTEMD_UNIT_PATH
    if [ $? -ne 0]
    then
      echo "failed to copy unit file"
      echo "exiting"
      exit 1
    fi

    echo "reloading systemd unit files"
    /bin/systemctl daemon-reload
    if [ $? -ne 0 ]
    then
      echo "failed to reload systemd untit files"
      echo "exiting"
      exit 1
    fi

    echo "enabling systemd unit file"
    /bin/systemctl enable $SYSTEMD_UNIT_FILE
    if [ $? -ne 0 ]
    then
      echo "failed to enable systemd untit files"
      echo "exiting"
      exit 1
    fi
  fi

  if [ $UNINSTALL -gt 0 ] || [ $PURGE -gt 0 ]
  then
    echo "stopping daemon"
    /bin/systemctl stop $SYSTEMD_UNIT_FILE
    if [ $? -ne 0 ]
    then
      echo "failed to stop daemon"
      echo "try to stop manually with:"
      echo "$ sudo systemctl stop $SYSTEMD_UNIT_FILE"
      echo "exiting"
      exit 1
    fi

    rm $SYSTEMD_UNIT_PATH
    if [ $? -ne 0 ]
    then
      echo "failed to remove unit file: $systemd_unit_path"
      echo "try to manually remove with:"
      echo "$ sudo rm $systemd_unit_path"
      ERRORS=$((ERRORS+1))
    fi

    echo "reloading systemd unit files"
    /bin/systemctl daemon-reload
  fi
}

function Help {
  echo print help here
}

## main program ##
INSTALL=1
UNINSTALL=0
PURGE=0
while getopts ":hup" option; do
  case ${option} in
  h) # display help
    Help
    exit;;
  u) # uninstall
    INSTALL=0
    UNINSTALL=1;;
  p) # uninstall and purge config files
    INSTALL=0
    UNINSTALL=1
    PURGE=1;;
  \?) # invalid option
    echo "error: unknown option: ${option}"
    echo 
    Help
    exit;;
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


#check_py_packages
#check_deb_packages
#copy_files
#create_pipenv
#install_plugin_requirements
install_executable
add_user

