# esf-format

A modern plain-text format for EVE Online ship fits.

The format looks familiar to anyone who knows EFT, but fixes the issues EFT has
with today's game: implants, mutations, fighter tubes, and more. It aims to be
easy for humans to write, and easy for computers to read and write.

This repository will be the home of the format, and will contain:

- The official grammar and rules, including a canonical form.
- A compact binary form, for URLs and storage.
- Examples, both valid and invalid.
- Tooling to validate documents against the canonical form.

The goal is one shared definition, so tools don't drift apart and fits move
cleanly between them.

## Status

The format is not final yet. The draft of `esf/1` is in [SPEC.md](SPEC.md),
and open for comments in [#1](https://github.com/EVEShipFit/esf-format/pull/1).
