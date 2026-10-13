# Saints Row 2 — Gentlemen of the Row + PC DLC Bridge

Run **Gentlemen of the Row (GotR) v1.9.2** and the **Kobraworks SR2 PC DLC** together on
**Juiced Patch**. Out of the box the two crash the game at startup; this bridge fixes that.

This repository contains **only a build script**. It does not include GotR, the DLC, Juiced or
any game files — you download those from their official sources and the script builds the
bridge on your PC from your own copies.

## Requirements

| | Version | Get it from |
|---|---|---|
| Saints Row 2 (PC) | Patch 1.2, **not** the German release | GOG or Steam |
| Juiced Patch | 9.2.0+ | [Kobraworks GitHub](https://github.com/kobraworksmodding/Saints-Row-2-Juiced-Patch/releases) |
| SR2 PC DLC | 1.0.1 | [Kobraworks / Saints Row Mods](https://www.saintsrowmods.com/forum/threads/sr2-pc-dlc.24993) |
| Gentlemen of the Row | 1.9.2 (`.rar`) | [Saints Row Mods (IdolNinja)](https://www.saintsrowmods.com/forum/threads/gentlemen-of-the-row.24/) |
| Python | 3.10+ | [python.org](https://www.python.org/downloads/) |

Install Juiced and the DLC first, the normal way. Do **not** install GotR with its own
patch builder — the bridge installs it as Juiced loose files.

## Install

```bat
python gotr_dlc_bridge.py build --game "C:\Program Files\GOG Galaxy\Games\Saints Row 2" --gotr "C:\Downloads\Gentlemen_of_the_Row_Saints_Row_2_Super_Mod_v1.9.2.rar"
python gotr_dlc_bridge.py install --game "C:\Program Files\GOG Galaxy\Games\Saints Row 2"
```

- `--gotr` accepts the downloaded `.rar` or the extracted folder.
- If the game is under `Program Files`, run `install`/`uninstall` from an **administrator** terminal.
- `install` backs up your `loose.txt` to `loose.txt.before_gotr_bridge` the first time.
- Back up your saves (`%LOCALAPPDATA%\THQ\Saints Row 2`) before changing mods. GotR recommends a new game.

Check or remove it any time:

```bat
python gotr_dlc_bridge.py check --game "<SR2 folder>"
python gotr_dlc_bridge.py uninstall --game "<SR2 folder>"
```

**Co-op:** both players need identical setups — same Juiced, DLC, GotR and bridge versions.

## What you get / what you give up

- ✅ All of Gentlemen of the Row
- ✅ DLC missions (Ultor Exposed, Corporate Warfare), vehicles, characters and multiplayer maps
- ❌ **DLC clothing** (111 items incl. the Unkut pack, and the Swat / Cop Uniform / Barbarian outfits)

The clothing loss is not a choice — see *Why* below.

## What the bridge changes

| Change | Reason |
|---|---|
| Skips GotR's `dlc04`/`dlc05` mission scripts (`.lua`, `.cts`) | The DLC ships newer, complete versions |
| Skips GotR's `em01.lua`, `rn07.lua` | Keeps Juiced's "TU3 Mission Fixes" versions |
| Removes GotR's `dlc04`/`dlc05` rows from `sr2_city_missions.xtbl` | **Crash #2** — both mods registered these missions |
| Removes GotR's `dlc04`/`dlc05` start navpoints from `mission_start_sr2_city.cts` | The DLC defines the same navpoints |
| Removes `thread_new("dlc04_main")` / `("dlc05_main")` from `sr2_city.lua` | Those functions exist nowhere; dead code |
| Adds empty `dlc_customization_items/outfits/stores.xtbl` overrides | **Crash #1** — DLC clothing can't fit (below) |

Everything else in GotR is installed byte-for-byte unchanged.

## Why (technical notes)

Found by decompiling `SR2_pc.exe` (GOG, patch 1.2) and measuring item counts in a running game.

**Crash #1 — clothing item limit.** SR2 stores customization items in a fixed array of
`0x41A` = **1050** entries (`cmp eax, 0x41A` at `0x7BBAC6`, array at `0x29E8CD0`, `0x78` bytes
each); extra items are silently skipped. Measured registered items:

| Setup | Items |
|---|---|
| Vanilla | 919 |
| Vanilla + DLC | 1029 |
| GotR | 1050 (GotR wants 1054 — it already loses 4 on its own) |
| GotR + DLC (needed) | 1164 → 114 over |

With GotR filling the array, none of the DLC's 110 items register. When Juiced merges the DLC
clothing stores, the store loader looks up a DLC item, gets NULL, and crashes reading
`item+0x2C` at `0x7BD6F1`. Nothing outside the three DLC clothing tables references those
items, so emptying them is safe.

**Crash #2 — duplicate missions.** GotR restored the Corporate Warfare missions `dlc04`/`dlc05`
in its `sr2_city_missions.xtbl`; the DLC registers them again. Juiced's DLC mission append then
gets a NULL mission in the unlock/reward loader and crashes writing `[esi+0xC8]` at `0x69F839`.

**Keeping the DLC clothing** would require raising the 1050-item engine limit, which has to be
done in Juiced itself. If that happens, this bridge can drop its clothing overrides.

## Credits

- **Gentlemen of the Row** — IdolNinja
- **Juiced Patch** and **SR2 PC DLC** — Kobraworks
- **Saints Row 2** — Volition / Deep Silver

This project is not affiliated with any of them. It redistributes none of their files.

## License

The bridge script is MIT licensed (see `LICENSE`). GotR, Juiced, the DLC and Saints Row 2 keep
their own licenses.
