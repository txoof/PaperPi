#!/usr/bin/env bash


APPNAME=paperpi
INCLUDE=tar_include.txt
EXCLUDE=tar_exclude.txt
VERSION=$(cat ../$APPNAME/my_constants.py | sed -ne 's/^VERSION\W\{0,\}=\W\{0,\}\(.*\)["'"'"']/\1/p')

TARFILE=../$APPNAME\_$VERSION.tgz
LATEST=../$APPNAME\_latest.tgz


function make_tar {
  echo "creating tar archive for $APPNAME V$VERSION"
  tar hcvzf $TARFILE -X $EXCLUDE -T $INCLUDE > /dev/null 2>&1
  cp $TARFILE $LATEST
}

make_tar
