"""A plugin that misbehaves on request, to test the runner.

The ``act`` setting says what one update does.
"""

import os
import signal
import subprocess
import sys
import time
from typing import Literal

from paperpi.plugin import NOTHING, Plugin, PluginSettings, alert, ready

Act = Literal["ok", "nothing", "alert", "raise", "hang", "exit", "crash", "kill", "child", "wrong"]


class Settings(PluginSettings):
    act: Act = "ok"


def fetch(context):
    act = context.settings.act
    if act == "nothing":
        return NOTHING
    if act == "alert":
        return alert("ALERT")
    if act == "raise":
        raise ValueError("data source said no")
    if act == "hang":
        time.sleep(3600)
    if act == "exit":
        sys.exit(4)
    if act == "crash":
        os._exit(3)
    if act == "kill":
        os.kill(os.getpid(), signal.SIGKILL)
    if act == "child":
        # A program started by the plugin that would outlive it if nobody stopped it.
        child = subprocess.Popen(["sleep", "3600"])
        (context.storage / "child.pid").write_text(str(child.pid))
        time.sleep(3600)
    if act == "wrong":
        return "not a Fetched"
    return ready("OK")


def draw(text, context):
    return {"text": text}


PLUGIN = Plugin(
    type="fake",
    description="Misbehaves on request.",
    settings=Settings,
    layouts={"one": {"column": [{"name": "text", "type": "text"}]}},
    fetch=fetch,
    draw=draw,
    sample="SAMPLE",
    refresh=30,
)
