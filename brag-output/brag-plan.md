# ARDA — brag plan

**What it is:** A Herdr plugin that lets AI agents in different harnesses, sessions and machines work as one team: they find each other by name, hand work over, and get results back.
**For:** Developers running Claude Code, Codex and others side by side, who are stuck being the human copy-paste relay.
**Sets it apart:** No daemon, no database, no MCP server: pure Python stdlib, Herdr does the routing.
**Best claim:** "Nobody relays anything."
**Visual hook:** Three agent panes, and an orange "YOU" cursor frantically ferrying text between them.
**Real UI shown:** `arda peers` output, `arda task @reviewer` → `delivered:`, the `[arda/1 task_request …]` prompt, `arda ack` / `arda result` (all from README/examples).
**Tone:** default → punchy, clean, a little smug. Hard-ish cuts on the beat.
**Share caption:** Your agents shouldn't need you as a copy-paste relay.

## Identity (user-supplied palette)
- Move Green `#1B3B28` canvas · Signal Lime `#92FF5F` accent · Soft White `#F7F7F2` text
- Orange `#FF7036` = the pain (human relay) · Ice `#BFF2F0` / Mint `#CFF1D2` = agent tints
- Type: Inter Display Black/Bold, tight tracking; Cascadia Mono for terminals.

## Storyboard (22s, 30fps, 120 BPM — bar = 2s)
| # | Time | Scene | On screen |
|---|---|---|---|
| 1 | 0–4s | Hook | 3 panes (@implementer claude, @reviewer codex, @tester). Orange "YOU" pill zips pane→pane with "copy… paste…". Headline: **"You are the relay."** |
| 2 | 4–7s | Reveal (drop) | Lime flood wipe. **ARDA** huge. "Agents shouldn't live in separate worlds." |
| 3 | 7–11s | Find | Terminal types `arda peers`, output lines stagger in across sessions/machines. Caption: **"Find each other by name."** |
| 4 | 11–16s | Hand off | Implementer types `arda task @reviewer …` → `delivered`. Lime packet flies to reviewer; reviewer shows task_request, `arda ack`, `arda result`; packet flies back. Caption: **"Hand off work. Get results back."** |
| 5 | 16–18.5s | Thin | Chips stamp: No daemon. / No database. / No MCP server. → "Pure Python stdlib." |
| 6 | 18.5–22s | Outro | **Different agents. One working team.** + `herdr plugin install Nirvaan05/arda` + ARDA mark. |

## Sound
Generated 120 BPM bed in A minor (Am–F–C–G), filtered/sparse hook, riser into the drop at 4.0s, full groove after. SFX in key: soft keyclicks, filtered whoosh for packets, A-pentatonic plucks for stamps; all mixed well under the music. Fade out last 1s.
