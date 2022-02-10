#!/usr/bin/env bash

APPNAME="paperpi"
LOCALPATH="../paperpi"
INSTALLPATH="/home/pi/src/install_loc"
CWD=$(pwd)

# core debian packages
INCLUDE="./install_include.txt"
EXCLUDE="./install_exclude.txt"


# install requirements from the plugin requirements-*.txt files
function install_plugin_requirements {
  pushd $INSTALLPATH/$APPNAME
  # find all the plugin requirements and install using pipenv install 
  tempfile=$(mktemp)
  find $CWD/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \; 
  echo "installing Plugin requirements:"
  cat $tempfile
  pipenv install -r $tempfile --skip-lock
}

# rsync the include files to the install path
function copy_files {

  echo "Installing files to $INSTALLPATH"
  rsync -a --exclude-from=$EXCLUDE --include-from=$INCLUDE $LOCALPATH $INSTALLPATH
  cp ./Pipfile $INSTALLPATH/$APPNAME

}

# create the pipenv for the install using the local python3 interpreter
function create_pipenv {
  pushd $INSTALLPATH/$APPNAME
  pipenv install --skip-lock
  popd

}


function check_packages {

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

}

check_packages
#copy_files
#create_pipenv
#install_plugin_requirements

