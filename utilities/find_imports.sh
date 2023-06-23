#!/usr/bin/env bash

PLUGIN_PATH="../paperpi/plugins/"


# local libraries can sometimes be picked up by pipreqs; these should not
# be included in the requirements file
IGNORE_MODULES=( "library" "ipython" )

for filename in $PLUGIN_PATH/*; do
  if [[ -f ${filename} ]]; then
    echo "skipping regular file: $filename"
    continue
  fi  

  basename=$(basename $filename)
  if [[ $basename != "_"* ]]; then
    echo "processing requirements for plugin: $basename"
    savepath=$filename/requirements-$basename.txt
    pipenv run pipreqs --no-follow-links --force --savepath $savepath $filename

    # remove trailing version number
    sed -i -E 's/==\S+$//g' $savepath

    # remove ignored modules
    for word in "${IGNORE_MODULES[@]}"; do
      sed -i -E "/$word/d" $savepath
    done
    

  fi
done
