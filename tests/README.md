# Test cases

Cases to test an esf/1 tool against. Each folder is one case, and its
`case.toml` names the spec section and the rule it tests.

- `valid/<case>/`: a valid document.
  - `input.esf` or `input.b64`: the document.
  - `canonical.esf`: its canonical form (§8).
  - `canonical.b64`: its binary form (§10).
- `invalid/<case>/`: a document a reader must reject.
  - `input.esf` or `input.b64`: the document.

`.b64` files hold the binary form as base64url (§10.4).

Names resolve against the latest SDE. Invalid cases only need to be
rejected; the error message is up to the tool.

## Testing your tool

Your tool needs three commands. Each reads a document, text or binary, from
stdin:

| command | output |
| --- | --- |
| `check` | Exit 0 if the document is valid, 1 if it is invalid. |
| `canonical` | The canonical text form, on stdout. |
| `binary` | The binary form as raw bytes, on stdout. |

Then run the cases against it, with [uv](https://docs.astral.sh/uv/):

```
uv run --project tools esf-test -- path/to/your-tool
```

Use `--no-canonical` or `--no-binary` to skip what your tool does not do,
and `-k <text>` to run only matching cases.

For a valid case, the runner checks that:

- `check` accepts the input;
- `canonical` turns the input, and `canonical.esf` itself, into `canonical.esf`;
- `binary` turns the input into `canonical.b64`;
- `check` accepts `canonical.b64`, and `canonical` turns it into `canonical.esf`.
