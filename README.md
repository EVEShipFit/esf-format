# esf-format

A modern plain-text format for EVE Online ship fits.

The format looks familiar to anyone who knows EFT, but fixes the issues EFT has
with today's game: implants, mutations, fighter tubes, and more. It aims to be
easy for humans to write, and easy for computers to read and write.

This repository is the home of the format:

- [SPEC.md](SPEC.md): the rules, including a canonical form.
- [grammar.ebnf](grammar.ebnf): the official grammar.
- [esf.proto](esf.proto): the schema of the compact binary form, for URLs and
  storage.

Still to come: examples, both valid and invalid, and tooling to validate
documents against the canonical form.

The goal is one shared definition, so tools don't drift apart and fits move
cleanly between them.

## Status

`esf/1` is a draft, and not final yet. It may still change in ways that break
existing documents.

Comments are welcome; please open an
[issue](https://github.com/EVEShipFit/esf-format/issues).
