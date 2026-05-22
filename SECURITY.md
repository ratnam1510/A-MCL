# Security Policy

## Supported versions

A/MCL is pre-1.0 software. Only the latest minor release on PyPI
(`pip install --upgrade amcl-server`) is supported with security fixes.

## Reporting a vulnerability

If you discover a security issue, please report it privately by emailing the
maintainer at **110657687+ratnam1510@users.noreply.github.com** (or by opening
a GitHub Security Advisory on the
[repository](https://github.com/ratnam1510/A-MCL/security/advisories/new)).

Please include:

- A description of the issue and its impact.
- Steps to reproduce, or a proof-of-concept.
- The version of `amcl-server` you tested against.

You can expect an initial response within 7 days. Please do not file public
GitHub issues for security problems until a fix is released.

## Scope

A/MCL stores all data locally in `~/.amcl/amcl.db` and does not transmit data
to any external service by default. The optional `amcl-server share` flow
uploads a redacted project snapshot to the configured share backend; bugs in
that redaction path are in scope.
