#!/usr/bin/env bash

PLUGIN_PATH="../paperpi/plugins/"

for filename in $PLUGIN_PATH/*; do
  basename=$(basename $filename)

  if [[ $basename != "_"* ]]; then
    savepath=$filename/requirements-$basename.txt
    pipenv run pipreqs --no-follow-links --force --savepath $savepath $filename

    sed -i -E 's/==\S+$//g' $savepath
  fi
done
