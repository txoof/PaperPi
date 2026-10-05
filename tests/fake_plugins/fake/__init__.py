"""A plugin that misbehaves on request, to test the runner.

The ``act`` setting says what one update does.
"""

import os
import signal
import subprocess
import sys
import time
from typing import Literal

from pydantic import SecretStr

from paperpi.plugin import NOTHING, Plugin, PluginSettings, alert, ready

Act = Literal[
    "ok", "nothing", "alert", "raise", "hang", "exit", "crash", "kill", "child", "leave_child",
    "secret", "wrong",
]  # fmt: skip


class Settings(PluginSettings):
    act: Act = "ok"
    key: SecretStr = SecretStr("")


def fetch(context):
    act = context.settings.act
    # Lets tests check that this process is gone afterwards.
    (context.storage / "plugin.pid").write_text(str(os.getpid()))
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
    if act in ("child", "leave_child"):
        # A program started by the plugin that would outlive it if nobody stopped it.
        child = subprocess.Popen(["sleep", "3600"])
        (context.storage / "child.pid").write_text(str(child.pid))
        if act == "child":
            time.sleep(3600)
    if act == "secret":
        raise ValueError(f"server refused key {context.settings.key.get_secret_value()}")
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
