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
- [tests](tests/README.md): valid and invalid documents, text and binary, to
  test your tool against.
- [tools](tools/README.md): a reference validator, and the runner for the
  tests.

## Status

`esf/1` is a draft, and not final yet. It may still change in ways that break
existing documents.

Comments are welcome; please open an
[issue](https://github.com/EVEShipFit/esf-format/issues).
