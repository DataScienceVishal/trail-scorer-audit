"""Constraint 4, as a test rather than as a sentence in the README.

`--disable-socket` is in `addopts`, so this passes because pytest-socket is
switched on and not because nothing here happens to open a connection. The
distinction matters: without the flag every other test in the suite would still
pass, and the claim that the audit runs with no network would be resting on
nobody having written a call yet.
"""

from __future__ import annotations

import socket

import pytest


def test_opening_a_socket_is_a_test_failure() -> None:
    with pytest.raises(BaseException) as raised:
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    assert "SocketBlocked" in type(raised.value).__name__


def test_the_only_module_that_reaches_the_network_does_not_do_it_on_import() -> None:
    """upstream.fetch shells out to git and is never called from the suite.

    pytest-socket installs its guards in pytest_runtest_setup, so collection is
    the one window where the flag is not in force. Nothing at module level in
    upstream.py may open anything, and importing it here is the check.
    """
    from trailaudit import upstream

    assert callable(upstream.fetch)
