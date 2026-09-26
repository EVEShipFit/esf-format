# esf/1

A modern plain-text format for EVE Online ship fits.

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

Everything after the type name is optional, and appears in the order shown:
charge, mutaplasmid, overrides, state, location, comment.

## Contents

1. [Premise](#1-premise)
2. [Examples](#2-examples)
3. [Tokens](#3-tokens)
4. [Reading a document](#4-reading-a-document)
5. [Placement](#5-placement)
6. [Semantics](#6-semantics)
7. [Grammar](#7-grammar)
8. [Canonical form](#8-canonical-form)
9. [EFT interop](#9-eft-interop)

## 1. Premise

A fit is a list of items. Anything the SDE already knows is left unwritten. A
launcher is a high slot because its power attribute says so; a subsystem is a
subsystem because its category says so.

Syntax appears where the SDE cannot answer: how many, what is loaded, what
state an item is in, where it sits when that is not the obvious place, and
where its attributes differ from the type's. Tactical modes are written
explicitly (§6.1).

Three properties follow:

- Racks and slot indices are unwritten in ordinary use.
- Blank lines are insignificant. Grouping is for the reader.
- Line order is insignificant, except for the version and hull lines, and for
  items that take a position - those in the same rack, and fighter squadrons -
  which are placed in the order they appear.

esf/1 describes the fit, and nothing around it. Skills, security status,
wormhole and other environment effects, and projected fits are not part of it.

This document defines how esf/1 must be read and written.

## 2. Examples

An ordinary fit. Nothing marks the racks; the grouping is for the reader only.

```
esf/1
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

A fit exercising every module construct at once. `- @high` holds the third
high slot open, so the guns take the first two and the nosferatu the fourth.
`@mid3` holds the second mid slot open (as nothing unpinned is left to fill it).

```
esf/1
Hecate "Sharpshooter Kite" /Sharpshooter

150mm Light AutoCannon II :Barrage S
150mm Light AutoCannon II :Republic Fleet Fusion S
- @high
Small Energy Nosferatu II

5MN Y-T8 Compact Microwarpdrive +Unstable {speedFactor 524, mass 45.2}
Warp Disruptor II @mid3

Damage Control II !off
Gyrostabilizer II !heat
Damage Control II @cargo          // spare

Zainou 'Gnome' Shield Management SM-703
Standard Blue Pill Booster
```

Drones and fighters. A deployed drone line repeats, so `5x Warrior II` is five
drones in space; a `@bay` line is one stack; a fighter line is one squadron, so
`9x Firbolg II` twice is two squadrons of nine, never one of eighteen.

```
esf/1
Thanatos "Ratting"

Drone Damage Amplifier II
Drone Damage Amplifier II

5x Warrior II
5x Hobgoblin II @bay

9x Firbolg II
9x Firbolg II
6x Dromi II
3x Cyclops II @bay
```

Two fits in one document: a Raven carrying a fitted Heron in its frigate escape
bay. The Heron exists only there, as it is referenced.

```
esf/1
Raven "Mission Runner"

4x Cruise Missile Launcher II :Scourge Cruise Missile
Large Shield Extender II

Heron "Scout" @frigate

esf/1
Heron "Scout"

Core Probe Launcher I :Core Scanner Probe I
Relic Analyzer I
```

A container in the cargo hold. It is its own fit, with the container as its
hull, and referenced like the Heron. What it holds is its cargo.

```
esf/1
Rifter "Roamer"

3x 200mm AutoCannon II :Republic Fleet EMP S
1MN Afterburner II

Small Secure Container "Spares"

esf/1
Small Secure Container "Spares"

1000x Republic Fleet EMP S
Damage Control II
```

## 3. Tokens

| token | name | meaning |
| --- | --- | --- |
| `Nx` | count | Prefix. How many. |
| `:` | charge | Ammunition or script loaded into this item, optionally with a count. |
| `+` | mutaplasmid | Declares the item abyssal. |
| `{ }` | overrides | Attribute values replacing the type's own. |
| `!` | state | `off`, `on`, `heat`. |
| `@` | location | `cargo`, `bay` for drones and fighters, another hold (§5.1), or a rack. An item names a rack only to pin a slot. |
| `"` | quoting | A fit name after a type name; otherwise a literal type name. |
| `/` | mode | Hull line only. Tactical mode, by name. |
| `-` | empty slot | Stands in for a type name. Takes a location, and an index pins it. On the hull line, no ship. |
| `//` | comment | To end of line. |

## 4. Reading a document

### 4.1 Lex - no SDE required

Split each line on spaces, except inside a `{ }` block or a quoted string,
each of which is scanned to its closing delimiter as one token. Inside a
quoted string, `""` is a literal `"`, not the closing delimiter. A token is
sigil-initial if its first character is one of `:` `+` `{` `!` `@` `"` `/`.
A token beginning with `//` is a comment; one beginning with a single `/` is a
mode.

A first token matching the count pattern is always the count. The type name
runs from the token after it to the next sigil-initial token or end of line.
A bare `-` there is the empty-slot marker, never a name. Past the first token,
`-` is part of the name: `Legion Defensive - Covert Reconfiguration`.

A version line starts a fit, and a document holds one or more fits (§6.12).
The hull line is the first line after the version line, skipping blank and
comment-only lines. It is required. Every other line is an item, a reference
or an empty slot. No lookup is needed to tell them apart.

A fit that could be wrong - powergrid, CPU, calibration, hardpoints,
bandwidth, tube count, squadron size, more modules than the rack holds, more
charges than the item holds, a hold the hull does not have - is still a valid
document.

### 4.2 Resolve - SDE required

Look up each name. Names are English SDE names; other languages are not
matched. Where a name is shared, a published type wins over an unpublished
one, then the lowest type ID wins. Category, group and dogma attributes
determine what the item is and where it belongs (§5). Rack indices are assigned
by counting occurrences. The hull line resolves to a Ship, Structure or
container, or is `-`.

## 5. Placement

Where an item goes when no `@` token says otherwise.

| resolves as | default placement |
| --- | --- |
| Ship, Structure, container | The hull line. Elsewhere, cargo. |
| Subsystem | Subsystem rack, next free index. |
| Rig | Rig rack, next free index. |
| Service module | Service rack, next free index. |
| Module | The rack named by its power attribute, next free index. |
| Drone | Deployed. |
| Fighter | One squadron, in the next free tube. |
| Charge | Attached by `:`, otherwise cargo. |
| Implant, Booster | Plugged in. |
| Ship Modifier | The hull line's `/mode`, and nowhere else. |
| anything else | Cargo. |

An `@` token overrides the default. `Damage Control II @cargo` is a spare in
the hold rather than a fitted module, `@bay` applies to drones and fighters,
and `@fuel` puts an item in the fuel bay.

An item names its rack only to pin a slot (§6.3). An empty slot always names
its rack.

### 5.1 Holds

Besides `cargo` and `bay`, a location names one of these holds. Nothing is
placed in them by default.

| location | hold | SDE attribute |
| --- | --- | --- |
| `ammo` | Ammo Hold | `specialAmmoHoldCapacity` |
| `booster` | Booster Hold | `specialBoosterHoldCapacity` |
| `command` | Command Center Hold | `specialCommandCenterHoldCapacity` |
| `corpse` | Corpse Hold | `specialCorpseHoldCapacity` |
| `depot` | Mobile Depot Hold | `specialMobileDepotHoldCapacity` |
| `expedition` | Expedition Hold | `specialExpeditionHoldCapacity` |
| `fleet` | Fleet Hangar | `fleetHangarCapacity` |
| `frigate` | Frigate Escape Bay | `frigateEscapeBayCapacity` |
| `fuel` | Fuel Bay | `specialFuelBayCapacity` |
| `gas` | Gas Hold | `specialGasHoldCapacity` |
| `ice` | Ice Hold | `specialIceHoldCapacity` |
| `infrastructure` | Infrastructure Hold | `specialColonyResourcesHoldCapacity` |
| `maintenance` | Ship Maintenance Bay | `shipMaintenanceBayCapacity` |
| `mineral` | Mineral Hold | `specialMineralHoldCapacity` |
| `mining` | Mining Hold | `generalMiningHoldCapacity` |
| `moon` | Moon Material Output Bay | `outputMoonMaterialBayCapacity` |
| `planetary` | Planetary Commodities Hold | `specialPlanetaryCommoditiesHoldCapacity` |
| `quafe` | Quafe Hold | `specialQuafeHoldCapacity` |
| `subsystem` | Subsystem Hold | `specialSubsystemHoldCapacity` |

## 6. Semantics

### 6.1 Tactical modes

A Tactical Destroyer is always in one of three tactical modes: Defense,
Propulsion or Sharpshooter. The SDE has each mode as its own unpublished type,
in the Ship Modifiers group, one set per hull.

A tactical mode is written on the hull line as `/name`, and nowhere else. At
most one per fit.

The value is a name, resolved against the modes belonging to the hull on the
same line. A mode's name starts with the hull's name, which may be left out.
What remains is matched by any leading run of whole words unambiguous among
them, folded as §6.10 says, so `/sharpshooter`, `/Sharpshooter Mode` and
`/Hecate Sharpshooter Mode` are equivalent. Canonical form leaves out the
hull's name and writes the shortest such run: `/Sharpshooter`.

### 6.2 Lines and counts

What a count means follows from where the line lands.

On a fitted or deployed item, `Nx` is repetition: `3x 200mm AutoCannon II` is
three lines naming that gun.

An item that is stored - in cargo, a bay or a hold - is a stack, and `Nx` is
the stack's size. A fighter line is a squadron, and `Nx` is the number of
fighters in it. Neither expands into repeated lines, and two such lines are two
stacks or two squadrons, never one.

Absent means one, except on a fighter line, where it means a full squadron.

A count and a pinned slot are mutually exclusive.

### 6.3 Positions

Slots are numbered from 1: `@low1` is the first low slot, `@low3` the third.

Items in the same rack with no `@` take the next free index in order of
appearance. `@low3` pins. Pinned lines are placed first, then unpinned lines
fill what remains, in order.

Fighter squadrons take their tube in line order, and are never pinned.

### 6.4 States

`!off` offline. `!on` online but not running. `!heat` overloaded, which
implies running.

A line with no state token takes a default. A fitted or deployed item defaults
to running when its type has a dogma effect in the active or target category,
and to online otherwise.

A stored item has no state, and a state token on it is invalid.

### 6.5 Charges

`:` names the charge loaded into the item on its line. A count after the `:`
is how many are loaded: `Bomb Launcher I :1x Void Bomb`. Without one, the item
is fully loaded.

A count at the start of the line counts modules, not charges:
`3x Light Missile Launcher II :7x Scourge Light Missile` is three launchers
holding seven missiles each. Spare ammunition is a separate cargo line.

### 6.6 Attribute overrides

`{ }` lists attributes as name value pairs separated by commas, using SDE
attribute names. Values are absolute: `speedFactor 524`. Each replaces the
type's base attribute value, and everything the engine computes on top of it
still applies. An attribute that is not listed keeps its base value.

`+name` before the braces declares the item abyssal and names the mutaplasmid
applied to the base type on the same line. It is matched by any leading run
of whole words unambiguous among those applicable to that base, folded as §6.10
says, so `+Unstable` and `+Unstable Microwarpdrive Mutaplasmid` are
equivalent.

Without `+`, the braces are a plain override and the item remains its own
type.

### 6.7 Empty slots

`- @high` reserves one slot; `3x - @high` reserves three; `- @high4` reserves
that one.

### 6.8 Comments

`//` to end of line. Not part of the fit, and dropped by canonicalisation.

### 6.9 Quoted names

A type name may be written in double quotes: `"Weird/Name II"`. Quoting is
required for a name whose first word begins with `-`, or in which any word is
sigil-initial (§4.1), and is permitted anywhere. Inside quotes, a double
quote is written twice: `"Oracle ""Blaze"" Squadron SKIN"`.

A quoted string after the type name is a fit name, on the hull line and in a
reference (§6.12). Canonical form quotes only where required.

### 6.10 Whitespace and encoding

UTF-8. LF or CRLF. Leading and trailing spaces on a line are insignificant.
Runs of spaces between tokens are one separator.

Names match case-insensitively, by locale-independent Unicode simple case
folding.

### 6.11 Version

`esf/N` starts every fit, so it is the first line of every document. It
identifies the format version, and is required.

This document defines version 1. A reader rejects any `N` it does not
implement.

### 6.12 Multiple fits

A document holds one or more fits, each starting with its own version line.
Two documents joined together are one valid document.

A container is a type in the Cargo Container, Secure Cargo Container, Audit
Log Secure Container or Freight Container group.

A Ship, Structure or container line followed by a quoted fit name is a
reference: that fit, stored where the line lands. `Heron "Scout" @frigate` puts
the Heron fit named `Scout` in the frigate escape bay. It matches the fit in
the same document with that hull and that fit name, folded as §6.10 says, and
is invalid unless exactly one fit matches. A reference takes a count and a
location, and nothing else.

A fit that is referenced exists only where it is referenced, once per
reference and count. A fit that is not referenced stands on its own. No fit
may contain itself, directly or through another fit.

A Ship or Structure line without a fit name is an unfitted hull, and a
container line without one is an empty container.

A hull line of `-` is a fit without a ship: a plain list of items, such as a
contract. Every line in it is stored in cargo, and any other location or an
empty slot is invalid. It may have a fit name, but no mode.

A hull line naming a container is read the same way, and its cargo is what the
container holds.

## 7. Grammar

The grammar is in [grammar.ebnf](grammar.ebnf).

EBNF per XML 1.0 §6 (Notation). Alternatives are tried in the order written.
Terminals are characters, not bytes; §6.10 gives the encoding.

A document that does not end in an `eol` is read as if it did.

## 8. Canonical form

For hashing, diffing, URLs and cross-tool comparison. Two documents describe
the same fit if and only if their canonical forms are byte-identical, and
`canonical(canonical(x)) == canonical(x)`.

Canonical form is minimal: it writes only what cannot be derived from the line
itself. In practice it is close to what a person writes by hand.

- Fits keep their order in the document, with one blank line between them.
  Each is written as follows.
- `esf/1`, then the hull line - type name, quoted fit name, and `/mode` as
  §6.1 writes it where the hull has one - then a blank line.
- Groups in this order, one blank line between them: subsystems, high, mid,
  low, rig, service, drones, fighters, cargo, the holds of §5.1 in the order
  listed, implants, boosters. An empty group is omitted.
- Within a rack, and among fighters, line order is the position. Every other
  group is sorted by type name folded as §6.10 says, then by the whole
  canonical line compared byte by byte.
- A rack is written in slot order, occupied and empty lines alike, so a line's
  place in that run is its position. No line carries an index.
- An empty-slot line after the last occupied slot in its rack is dropped.
- Adjacent identical lines collapse into one count: fitted items, deployed
  items, and empty slots. Stacks and squadrons never collapse.
- A modifier is written only where it differs from the item's default: a state
  that is not the one §6.4 gives it, a location that is not its default
  placement, a charge count where the item is not fully loaded.
- Type names are the English SDE name at the SDE's casing, quoted only where
  §6.9 requires it. A reference writes the fit name as the referenced hull
  line does.
- Overrides are sorted by attribute name. An abyssal item names its
  mutaplasmid by the shortest unambiguous leading run of words and writes every
  rollable attribute; a plain override writes only the attributes given.
- Modifiers are written charge, mutaplasmid, overrides, state, location.
- A number is the shortest decimal that reads back as the same value.
- Comments dropped. One space between tokens, LF endings, no trailing
  spaces, one trailing newline.

Canonicalisation keeps the fit, and drops its presentation: grouping,
comments and shorthand.

## 9. EFT interop

Both directions are normative, so that every tool converts identically.

### 9.1 EFT in

`[Ship, Name]` becomes the hull line. `, Charge` becomes `:Charge`.
`/OFFLINE` becomes `!off`. `Item xN` becomes `Nx Item`. Drone entries become
deployed lines, matching §5. Blank-line grouping is discarded and racks are
re-derived.

`[Empty X slot]` becomes an empty-slot line, by this mapping:

| EFT | esf |
| --- | --- |
| `[Empty High slot]` | `- @high` |
| `[Empty Med slot]` | `- @mid` |
| `[Empty Low slot]` | `- @low` |
| `[Empty Rig slot]` | `- @rig` |
| `[Empty Subsystem slot]` | `- @sub` |
| `[Empty Service slot]` | `- @svc` |

### 9.2 EFT out

EFT carries less than esf. Some constructs are dropped outright, others are
flattened onto what EFT does have.

| construct | EFT output |
| --- | --- |
| several fits | one EFT fit each, referenced ones included |
| references | hull type emitted in the cargo block |
| container contents | also emitted in the cargo block |
| `-` or container hull | not convertible |
| `/mode` | dropped |
| `!heat`, `!on` | dropped |
| charge counts | dropped |
| `+` and `{ }` | base type emitted, overrides dropped |
| `@high3` pins | line order, with `[Empty High slot]` for the gaps |
| `@cargo` spare | emitted in the cargo block |
| deployed vs `@bay` | both emitted in the drone block |
| other holds | emitted in the cargo block |
| squadron counts | summed into a fighter total |
| implants, boosters | dropped |
| comments | dropped |
