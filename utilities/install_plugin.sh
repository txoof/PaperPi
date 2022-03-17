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

INSTALLPATH="/usr/local/paperpi"

function abort {
  # abort installation with message
  printf "Aborting install: \n\n"
  printf "%s\n" "$@"
  printf "%s\n\nThis installer can be resumed with:\n"
  printf "sudo $SCRIPT_DIR/$(basename "$0")\n"
  exit 1
}

function check_permissions {
  if [ "$EUID" -ne 0 ]
  then
  abort "

  Insufficient privleges to install plugin.

  Try:
    $ sudo $0 $1

  This installer must be run with superuser privleges will 
  and install a plugin "$1" into $INSTALLPATH.

"
  fi
}

# function stop_daemon {
  
# }

# function decompress_plugin {
#     echo 'installing from $1'
#     tar -C $TMP_PATH -xvf $1
#     echo $TMP_PATH
    

# }

# function install_plugin {
#     echo ""
# }

# function check_permissions {
#   if [ "$EUID" -ne 0 ]
#   then
#     echo "

#   Try:
#     $ sudo $0

#   This installer will setup/uninstall $APPNAME to run at system boot and does the following:
#   * copy $APPNAME excutable to $BINPATH
#   * create configuration files in $SYSTEM_CONFIG_PATH
#   * setup systemd unit files in $SYSTEMD_UNIT_FILE_NAME
#   * add user "$APPNAME" to the GPIO and SPI access groups

#   To uninstall or purge all files use:
#   $ $0 -u|-p
# "
#   exit 0
#   fi
# function check_deb_packages {

#   if [ $INSTALL -lt 1 ]
#   then
#     # nothing to do here if not installing
#     echo ""
#   else
#     echo "checking for required debian packages"
#     halt=0

#     missing=()

#     # get all the debian_packages-*.txt
#     array=()
#     find $LOCALPATH -name "debian_packages-*.txt" -print0 >tmpfile
#     while IFS=  read -r -d $'\0'; do
#         array+=("$REPLY")
#     done <tmpfile
#     rm -f tmpfile

#     # source all the DEBPKG variables 
#     PKGS=()
#     PKGS+=(${CORE_DEB[@]})

#     for i in "${array[@]}"
#     do
#         echo "found debian packages for PaperPi module $(basename $i)"
#         source "$i"
#         for i in "${DEBPKG[@]}"
#         do
#           echo "checking $i"
#           if [ $(dpkg-query -W -f='${Status}' $i | grep -c "ok installed") -eq 0 ]
#           then
#             echo ""
#             echo "missing $i"
#             echo ""
#             halt=$((halt+1))
#             missing+=( $i )
#           fi
#         done
#     done

#     if [[ $halt -gt 0 ]]
#     then
#       echo "$halt required packages are missing."
#       echo "install missing packages with: "
#       echo "sudo apt install ${missing[*]}"
#       echo ""
#       echo "stopping install"

#       abort
#     else
#       echo "required packages installed"
#     fi
#   fi

# }


# function install_plugin_requirements {

#   if [ $INSTALL -gt 0 ]
#   then
#     echo "Installing requirements in virtual environment for $APPNAME plugins"
#     pushd $INSTALLPATH/$APPNAME
#     # find all the plugin requirements and install using pipenv install 
#     tempfile=$(mktemp)
#     find $SCRIPT_DIR/../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \; 
#     echo "installing Plugin requirements:"
#     cat $tempfile
#     if ! command pipenv install -r $tempfile --skip-lock
#     then
#       popd
#       abort "failed to install python modules" 
#     fi
#     popd
#   else
#     echo ""
#   fi

# }

# check_permissions
TMP_PATH=$(mktemp -d)

# decompress_plugin $1