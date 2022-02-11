#!/usr/bin/env bash

function install_devel_requirements {
  "installing all plugin development requirements"
  # find all the plugin requirements and install using pipenv install
  tempfile=$(mktemp)
  find ../paperpi/plugins -type f -name "requirements-*.txt" -exec cat {} >> $tempfile \;
  echo "Installing development dependencies for all plugins:"
  cat $tempfile
  pipenv install --dev -r $tempfile --skip-lock
}

function clean_devel {
  echo "removing all previous development modules"
  pipenv uninstall --all-dev --skip-lock
}

clean_devel
install_devel_requirements
