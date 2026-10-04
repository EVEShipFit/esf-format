# esf-format

A modern plain-text format for EVE Online ship fits.

```
%esf/1
Rifter "Shield Buffer"

3x 200mm AutoCannon II :Republic Fleet EMP S
Small Energy Nosferatu II

1MN Afterburner II
Warp Scrambler II
Medium Shield Extender II

Damage Control II
Gyrostabilizer II
Overdrive Injector System II

2x Small Projectile Collision Accelerator I
Small Polycarbon Engine Housing I

1000x Republic Fleet EMP S @cargo
```

If you know EFT, you can already read this. That is the point.

## Why esf?

- **Write it by hand.** One item per line. No racks to keep in order, no
  `[Empty High slot]` lines.
- **Order and blank lines don't matter.** Group your fit however reads best.
- **Covers today's game.** Implants, boosters, abyssal modules, tactical modes,
  fighter squadrons, every special hold, and ships inside ships.
- **One fit, one text.** A canonical form gives every fit exactly one way to be
  written, so tools can hash, diff and compare fits.
- **Small enough for a URL.** A compact binary form, encoded as Protocol
  Buffers, fits a whole fit in a link.

## Everything on one line

Each line is a type name, with a few optional extras after it:

```
2x 150mm Light AutoCannon II :Barrage S !heat   // spare
│  │                         │          │       │
│  │                         │          │       └─ comment
│  │                         │          └───────── state
│  │                         └──────────────────── charge
│  └────────────────────────────────────────────── type name
└───────────────────────────────────────────────── count

5MN Microwarpdrive II +Unstable {speedFactor 524} @cargo
│                     │         │                 │
│                     │         │                 └─ location
│                     │         └─────────────────── overrides
│                     └───────────────────────────── mutaplasmid
└─────────────────────────────────────────────────── type name
```

That is most of the format. A few more things it can do:

```
%esf/1
Hecate "Sharpshooter Kite" /Sharpshooter    // tactical mode

150mm Light AutoCannon II :Barrage S
- @high                                     // keep a slot empty
Damage Control II !off                      // offline module
Damage Control II @cargo                    // a spare in the hold

Zainou 'Gnome' Shield Management SM-703     // implants just work
```

## Learn more

- [SPEC.md](SPEC.md): the full rules, with more examples.
- [grammar.ebnf](grammar.ebnf): the official grammar.
- [esf.proto](esf.proto): the schema of the compact binary form.

## Validate your tool

This repository has [test cases](tests) for every rule in the spec, text and
binary, and a runner that checks your tool against them. You need
[uv](https://docs.astral.sh/uv/).

1. Give your tool three commands. Each reads a document, text or binary, from
   stdin:

   | command | what it does |
   | --- | --- |
   | `your-tool check` | Exits 0 if the document is valid, 1 if it is invalid. |
   | `your-tool canonical` | Prints the canonical text form. |
   | `your-tool binary` | Prints the binary form, as raw bytes. |

2. Run the cases against it, from a clone of this repository:

   ```
   uv run --project tools esf-test -- path/to/your-tool
   ```

3. Fix what fails. Each failure names the case, the spec section, and the rule:

   ```
   FAIL invalid/pin-twice (§6.3): Two lines cannot pin the same slot.
     accepted an invalid document
   ```

Only reading fits? Add `--no-canonical` and `--no-binary`. To run some cases,
add `-k <text>`, such as `-k mutaplasmid`.

### The test cases

Each folder in [tests/valid](tests/valid) and [tests/invalid](tests/invalid)
is one case. Its `case.toml` says which rule it tests:

| file | what it is |
| --- | --- |
| `input.esf` or `input.b64` | The document. |
| `canonical.esf` | Valid cases only: its canonical form. |
| `canonical.b64` | Valid cases only: its binary form. |

`.b64` files hold the binary form as base64url. Type names are looked up in
the latest SDE. An invalid case only has to be rejected; the error message is
up to your tool.

### Check a single fit

The runner tests against a reference implementation, which you can also use
by itself:

```
uv run --project tools esf check fit.esf        # exit 0 if valid, 1 if not
uv run --project tools esf canonical fit.esf    # print the canonical form
uv run --project tools esf binary --b64 fit.esf # print the binary form
```

It reads text or binary, from a file or stdin. The first run downloads the
SDE into `~/.cache/esf/`; `uv run --project tools esf sde` updates it.

Its code lives in [tools/src/esf](tools/src/esf), with each file naming the
spec sections it implements. [tools/src/esf_tools](tools/src/esf_tools) holds
the rest: the SDE download, the command line and the test runner.

## Status

`esf/1` is a draft, and not final yet. It may still change in ways that break
existing documents.

Comments are welcome; please open an
[issue](https://github.com/EVEShipFit/esf-format/issues).
