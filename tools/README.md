# esf tools

A reference implementation of esf/1, and the runner for the
[test cases](../tests/README.md).

```
uv run esf check fit.esf        # exit 0 if valid, 1 if invalid
uv run esf canonical fit.esf    # print the canonical form
uv run esf binary --b64 fit.esf # print the binary form, as base64url
uv run esf sde                  # download the latest SDE
```

Input is text or binary, from a file or stdin. With `--b64`, binary input
and output are base64url.

The SDE is downloaded on first use, and cached in `~/.cache/esf/sde.json`;
set `ESF_SDE` to use another path. Run `esf sde` to update it.
