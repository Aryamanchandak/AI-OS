Assuming this is for German (Netzwerk neu vocab/phrases) and mobile-first. Say the word if it's a different domain — the gender-coding and compound-noun handling below only earn their place for German.

## 1. Card data model

Design the schema before the pixels, or the UI will fight it.

```
Card {
  id, deck_id, unit            // "Netzwerk A1, Kap. 4"
  front: { term, article?, plural?, ipa? }
  back:  { gloss, example_de, example_en, note? }
  audio_url?, image_url?
  tags[]                       // noun, trennbar, Akkusativ...
  srs: { due, stability, difficulty, reps, lapses, state }
}
```

Article and plural as **separate fields**, not baked into the term string — that's what lets you color-code gender, quiz plurals independently, and render `der Schlüssel · die Schlüssel` cleanly.

## 2. Screen inventory

Five screens, no more: **Decks → Session → Card detail → Stats → Add/Import**. Everything else is a sheet.

## 3. The study screen (where all the beauty budget goes)

**Layout.** One card, no chrome competing with it. Card occupies ~88% of viewport width, ~52% height, vertically centered but pushed *down* ~6% so the thumb reaches the grade row without a hand shuffle. Safe-area insets respected on both ends.

**Progress.** A 2px hairline at the top, segmented by remaining new / learning / review in three tints — not a "12/40" counter. Counters induce grinding; a shrinking bar induces flow.

**Reveal.** Tap anywhere, or swipe up. 3D flip on the Y axis, 320ms, `cubic-bezier(.2,.8,.2,1)`, `backface-visibility: hidden`, `perspective: 1200px`. The back face is *not* a new card — same paper, answer slides in from 6px below with a 40ms stagger between gloss and example sentence.

**Grading.** Two paths to the same four grades:
- Buttons: Again / Hard / Good / Easy in the bottom row, 48px tall, equal width, labeled with next-interval underneath (`10m`, `1d`, `4d`, `9d`). Showing the interval is the single highest-value micro-detail in any SRS UI.
- Gestures: left = Again, right = Good, up = Easy, down = Hard. Card follows the finger, `rotate = dx * 0.04deg`. Target label fades 0→1 over the first 120px of travel, edge of the screen picks up a soft directional tint. Under threshold → spring back (`stiffness 300, damping 30`). Over → throw off-screen in 220ms ease-out.

**Next card** rises from `scale(.94) translateY(8px)` → rest, 260ms. Never a hard cut.

## 4. Visual system

**Type.** Two families max. Term in a high-contrast display face — Fraunces or Instrument Serif — at 36–44px, optically tightened `-0.02em`. Everything else in Inter or Geist. Example sentence 17px / 1.55 line-height. Chrome 13px, uppercase, `+0.08em` tracking. **Verify ß, ä/ö/ü, and small-caps coverage before committing** — plenty of display faces ship broken umlauts at weight extremes.

**Compound nouns will break your layout.** `Geschwindigkeitsbegrenzung` is 27 characters. Auto-fit: step term size down 44 → 38 → 32 → 26px based on measured width, and allow a soft hyphenation break (`hyphens: auto; lang="de"`) only at the smallest step.

**Color.** Dark-first — you'll study at night. Base `#0A0A0B` (not pure black; pure black on OLED makes the scroll smear visible). Card surface `#141416` with a 1px `rgba(255,255,255,.06)` hairline. No drop shadows on static cards; one large soft ambient shadow on the actively dragged card only.

Gender accent as a 3px left rule on the card: der / die / das in three low-chroma hues (~35% saturation, matched luminance). This is functional, not decorative — over a few hundred reps it builds an associative hook. **Always pair it with the literal article text**; color alone fails for colorblind users and is bad pedagogy anyway.

**Grid.** 8px spacing scale, 20px card radius, 12px on buttons.

## 5. States you will otherwise forget

Nothing due · deck empty · first run · offline · audio missing · answer longer than the card · session complete (show retention % and a *stop* button, not "study more"). Design these before v1 ships; they're 30% of real usage.

## 6. Accessibility

44px minimum targets. `prefers-reduced-motion` → crossfade instead of flip, no throw. VoiceOver labels on grade buttons that include the interval. Haptic light-impact on grade, none on reveal.

## 7. Stack

PWA: **React + Vite + Tailwind + Framer Motion**, **Dexie/IndexedDB** for offline, **ts-fsrs** for scheduling. FSRS over SM-2 — better retention at equal workload, and it's a drop-in library. Installable to the home screen, no App Store, works on a plane. That matches the mobility-first constraint you build everything else against.

## 8. Phasing — and the part you won't like

**v1 (one weekend, hard stop):** one hardcoded deck from a JSON import, flip, four grades, FSRS, dark mode, session-complete screen. No settings. No deck management. No sync. No audio.

**v2:** TTS audio, stats, deck CRUD.
**v3:** LLM card generation from a Netzwerk unit, ingestion into the AI OS memory substrate.

The design above is deliberately over-specified so that v1 can be under-scoped without looking cheap. Given your own read on the 70%-and-stall pattern, the risk here isn't the design — it's building the deck-management layer before a single card has been reviewed. Ship v1 against one deck you actually need this week.

Want me to build v1 as a working HTML prototype you can flip through, or a Figma-style static mockup first?