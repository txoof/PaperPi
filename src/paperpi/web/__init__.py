"""The web interface: change PaperPi's settings from a phone or computer on the home network.

It runs inside ``paperpi run``, in its own thread (:mod:`paperpi.web.server`). The pages are
built on the Pi (:mod:`paperpi.web.app`). The password is scrambled, checked and saved by
:mod:`paperpi.web.password`; the log-in cookie is in :mod:`paperpi.web.auth`. See
``docs/decisions/web-interface.md``.
"""
