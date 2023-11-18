#!/usr/bin/env bash

# update the waveshare libraries from github and patch some known issues

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
PROJECT_DIR=$(dirname $SCRIPT_DIR)

# wavehsare repo
WS_REPO="https://github.com/waveshare/e-Paper.git"
WS_ROOT="e-Paper"
WS_LIB_PATH="RaspberryPi_JetsonNano/python/lib/waveshare_epd"

WS_LOCAL="$PROJECT_DIR/paperpi/waveshare_epd"

# git clone into temporary directory
# WS_TEMP=$(mktemp -d -t waveshare_XXXXX)

WS_TEMP="/tmp/waveshare_Yr5PG"

# git clone $WS_REPO $WS_TEMP
# if [[ $? -ne 0 ]]; 
# then
#   echo "failed to clone $WS_REPO"
#   echo "see $WS_TEMP"
#   exit 1
# fi

WS_VERSION=$(git --git-dir $WS_TEMP/.git log -1 --format=%h\ %ci)
echo "The current waveshare version is: $WS_VERSION"

# copy the downloaded libraries into the project directory
cp -r $WS_TEMP/$WS_LIB_PATH $PROJECT_DIR/paperpi/

# # add the latest commit to the constants file for record keeping
sed -i "s#\(ws_version\s\?=\).*#\1 '$WS_VERSION'#g" $PROJECT_DIR/paperpi/my_constants.py

echo "Patching issues with waveshare libraries"

# ## Patch issues with WaveShare Modules ##
# # remove unneeded numpy imports in waveshare modules
# find $WS_LOCAL -type f -exec sed -i 's/^import numpy/#&/' {} \;

# # add default value to `update` arg in init() method
  echo "  set update=false in init()"
find $WS_LOCAL -type f -exec sed -i -E 's/(^\W+def init\(self,\W+update)/\1=False/g' {} \;

# # add default value to `color` arg in Clear() method (see epd2in7 for example)
# find $WS_LOCAL -type f -exec sed -i -E 's/(\W+def Clear\(self,\W+color)\)/\1=0xFF)/' {} \;

# # default to full update in def init() for screens that support partial update
echo "  set default lut value in init()"
find $WS_LOCAL -type f -exec sed -i -E 's/(def init\(self, lut)(.*)/\1=None\2\n        if not lut:\n            lut = self.lut_full_update/' {} \;

# To resolve the issue below (wrong OS detected), replace a line in epdconfig.py
# https://github.com/waveshareteam/e-Paper/issues/306
echo "  patch wrong os detection in epdconfig.py"
sed -i "s|if os.path.exists('/sys/bus/platform/drivers/gpiomem-bcm2835'):|if os.path.exists('/etc/issue'):|" $WS_LOCAL/epdconfig.py