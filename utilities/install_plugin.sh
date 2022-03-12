#! /usr/bin/env bash

# stop running instance of PaperPi (daemon)
# decompress plugin tar
# copy the plugin into the PaperPi/plguins/directory
#   do some checking that it will not clobber an existing plugin w/out confirmation
# install any debian or python requirements
#   prompt the user to handle the debian reqs first?
#   install the python reqs automatically
# add plugin configuration to user/etc config files
#   prompt user to edit config files and manage settings
#   display a sample of the config so the user knows what to look for
# clean up temp files
# prompt user to restart paperp
#  optionallyr restart automatically (dubious)



function decompress_plugin {
    echo 'installing from $1'
    tar -C $TMP_PATH -xvf $1
    echo $TMP_PATH
    

}

function install_plugin {
    echo ""
}

unction check_deb_packages {

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

TMP_PATH=$(mktemp -d)

decompress_plugin $1