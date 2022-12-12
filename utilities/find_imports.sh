#!/usr/bin/env bash

PLUGIN_PATH="../paperpi/plugins/"

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

    sed -i -E 's/==\S+$//g' $savepath
  fi
done
