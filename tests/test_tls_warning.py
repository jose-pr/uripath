"""Turning TLS verification off is logged as a warning each time an object that
does it is made; verifying, or trusting a context the caller gave, logs
nothing."""

from __future__ import annotations

import logging
import ssl

import pytest

from uripath.schemes import FTPURIBackend, HTTPTransport

BUILDERS = {
    "http": lambda **options: HTTPTransport(**options),
    "ftp": lambda **options: FTPURIBackend(**options),
}


@pytest.fixture(params=sorted(BUILDERS))
def build(request):
    return BUILDERS[request.param]


def _warnings(caplog):
    return [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_building_with_verification_off_logs_a_warning_each_time(build, caplog):
    with caplog.at_level(logging.WARNING, logger="uripath"):
        build(verify=False)
        build(verify=False)
    records = _warnings(caplog)
    assert len(records) == 2
    assert all(r.name.startswith("uripath.") for r in records)
    assert all("not verified" in r.getMessage() for r in records)


def test_building_with_verification_on_logs_nothing(build, caplog):
    with caplog.at_level(logging.DEBUG, logger="uripath"):
        build()
        build(verify=True)
    assert _warnings(caplog) == []


def test_a_context_the_caller_gave_wins_over_verify_and_logs_nothing(build, caplog):
    context = ssl.create_default_context()
    with caplog.at_level(logging.DEBUG, logger="uripath"):
        build(ssl_context=context, verify=False)
    assert _warnings(caplog) == []
