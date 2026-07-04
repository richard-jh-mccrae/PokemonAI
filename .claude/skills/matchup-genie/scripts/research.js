export const meta = {
  name: 'matchup-genie-research',
  description: 'Archetype-parameterized web research for how ONE opponent Pokemon TCG deck wins AND how it is beaten: parallel archetype sweep (gameplan + optimal lines) + counterplay/weakness sweep + per-key-card deep dives (its threats + engine — how they function and how to neutralize), adversarially verified against engine card facts, synthesized into an objective counterplay doctrine with citations. Driven entirely by `args` (archetype/facts/gameplan/angles/key_cards) — never hardcode a deck here.',
  phases: [
    { title: 'Sweep', detail: 'parallel web searches: how it wins + how to beat it' },
    { title: 'Cards', detail: 'one deep-dive agent per key threat/engine card' },
    { title: 'Read', detail: 'deep-fetch the promising sources from the sweep' },
    { title: 'Verify', detail: 'adversarially check each claim against engine card facts' },
    { title: 'Synthesize', detail: 'objective counterplay doctrine + threats/targets + explicit gaps' },
  ],
}

// ── Inputs (all from `args`; the SKILL gathers these from the engine dump + Phase-1 overview) ──
// NOTE: the Workflow harness delivers a nested `args` object JSON-STRINGIFIED (typeof args === 'string'),
// so reading `args.archetype` directly yields undefined and the whole sweep silently no-ops. Parse
// defensively — works whether args arrives as a string (current harness) or an object (contract).
let ARGV
try {
  ARGV = (typeof args === 'string') ? JSON.parse(args) : (args || {})
} catch (e) {
  throw new Error(`matchup-genie-research: could not parse args (${String((e && e.message) || e)}). ` +
    `Invoke as Workflow({ scriptPath, args: { archetype, gameplan, facts, angles:[...], key_cards:[...] } }). ` +
    `Raw args prefix: ${String(args).slice(0, 200)}`)
}

const ARCH = ARGV.archetype || 'this opponent deck'
const FACTS = ARGV.facts || '(no engine facts supplied — flag this as a gap)'
const GAMEPLAN = ARGV.gameplan || '(how it wins not yet confirmed)'
const ANGLES = ARGV.angles || []                           // [{key, q}] — include a "counters" angle
const KEY_CARDS = ARGV.key_cards || []                     // [{name, why}] — its threats + engine

// Fail LOUDLY rather than silently running an empty sweep (the original args-binding bug's symptom:
// 0 angles · 0 key cards · 0 sources · only the self-serving synth agent ran).
if (ANGLES.length === 0 && KEY_CARDS.length === 0) {
  throw new Error(`matchup-genie-research: no angles AND no key_cards after parsing args — refusing to ` +
    `run an empty sweep. typeof args=${typeof args}; parsed keys=${JSON.stringify(Object.keys(ARGV))}. ` +
    `Ensure the Workflow call passes args: { archetype, gameplan, facts, angles:[...], key_cards:[...] }.`)
}

// Shared preamble: the set is the physical/online TCG (NOT Pocket); the simulator's card facts OVERRIDE
// any web guide (Scarlet & Violet Mega era + simulator deltas — see CLAUDE.md / docs/rules.md). FACTS is
// ground truth; the web is a prior. We research an OPPONENT deck to beat it — objective, deck-neutral.
const TCG = `You research the Pokemon Trading Card Game (the physical/online TCG — NOT Pokemon TCG Pocket, the mobile app). This is a competitive OPPONENT deck we want to beat. How it wins:\n${GAMEPLAN}\n\nEngine-confirmed card facts for THIS deck (ground truth — the simulator's stats/costs/text OVERRIDE any web guide; use these to judge relevance and catch misreads):\n${FACTS}\n\nWrite objectively about the opponent deck — how it functions and how it is countered — NOT relative to any one of our decks.`

const SWEEP_SCHEMA = { type: 'object', additionalProperties: false, required: ['urls', 'notes'],
  properties: {
    urls: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['url', 'title', 'why'],
      properties: { url: { type: 'string' }, title: { type: 'string' }, why: { type: 'string' } } } },
    notes: { type: 'string' },
  } }

const CARD_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['card', 'function', 'is_threat', 'is_target', 'neutralize', 'facts_conflict', 'sources', 'confidence'],
  properties: {
    card: { type: 'string' },
    function: { type: 'string', description: 'what this card does for the opponent deck — its job' },
    is_threat: { type: 'boolean', description: 'an attacker/ability we must respect' },
    is_target: { type: 'string', enum: ['fragile_preevo', 'prize_liability', 'engine', 'no'], description: 'if a disruption/snipe target, its Dossier role; else "no"' },
    neutralize: { type: 'string', description: 'how we blunt it: gust / snipe / disrupt / out-tempo / play around — concrete, deck-neutral' },
    facts_conflict: { type: 'string', description: 'any web claim that conflicts with the engine FACTS, or "none"' },
    sources: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'url'],
      properties: { title: { type: 'string' }, url: { type: 'string' } } } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  } }

const READ_SCHEMA = { type: 'object', additionalProperties: false, required: ['url', 'about_this_deck', 'claims'],
  properties: {
    url: { type: 'string' },
    about_this_deck: { type: 'string', enum: ['yes', 'no', 'unsure'] },
    claims: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['topic', 'claim'],
      properties: { topic: { type: 'string', enum: ['gameplan', 'tempo', 'weakness', 'counter', 'threat', 'matchup', 'tech', 'other'] },
        claim: { type: 'string' } } } },
  } }

const VERIFY_SCHEMA = { type: 'object', additionalProperties: false, required: ['verdict', 'note'],
  properties: { verdict: { type: 'string', enum: ['supported', 'contradicts_facts', 'about_different_deck', 'unverifiable'] },
    note: { type: 'string' } } }

const SYNTH_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['how_it_wins', 'tempo', 'weaknesses', 'threats', 'targets', 'counter_lines', 'gaps', 'sources', 'confidence'],
  properties: {
    how_it_wins: { type: 'string' },
    tempo: { type: 'string', enum: ['fast', 'midrange', 'slow'] },
    weaknesses: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['seam', 'exploit'],
      properties: { seam: { type: 'string' }, exploit: { type: 'string', description: 'objective, deck-neutral counterplay' } } } },
    threats: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['card', 'why'],
      properties: { card: { type: 'string' }, why: { type: 'string' } } } },
    targets: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['card', 'role', 'why'],
      properties: { card: { type: 'string' }, role: { type: 'string', enum: ['fragile_preevo', 'prize_liability', 'engine'] }, why: { type: 'string' } } } },
    counter_lines: { type: 'array', items: { type: 'string' }, description: 'concrete objective lines that beat the deck' },
    gaps: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'url'],
      properties: { title: { type: 'string' }, url: { type: 'string' } } } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  } }

log(`researching counterplay vs ${ARCH}: ${ANGLES.length} sweep angles · ${KEY_CARDS.length} key cards`)

// ── Round 1 — sweep + per-key-card deep dives, all at once (shared concurrency pool) ──
const [swept, cardFindings] = await Promise.all([
  parallel(ANGLES.map(a => () =>
    agent(
      `${TCG}\n\nSEARCH ANGLE for the ${ARCH} archetype: ${a.q}\n\nRun 2-4 web searches and open the most relevant results. Prefer recent competitive sources (deck guides, tournament reports, meta articles, matchup/counter discussions, ladder lists). Return the URLs worth a deep read (url + title + why relevant) and put anything immediately useful in notes. If web tools are unavailable, say so in notes.`,
      { phase: 'Sweep', schema: SWEEP_SCHEMA, label: `sweep:${a.key}`, effort: 'low' }))),

  parallel(KEY_CARDS.map(c => () =>
    agent(
      `${TCG}\n\nDEEP-DIVE one key card in the ${ARCH} deck to understand HOW it functions for the opponent and HOW WE NEUTRALIZE it.\n\nCARD: ${c.name}\nWHY IT MATTERS: ${c.why || 'a threat or engine piece'}\n\nWeb-search this card BY NAME in the ${ARCH} context (e.g. "${c.name} ${ARCH}", "how to beat ${c.name}"), open the best results, and pin down: its job in the deck; whether it is a THREAT (attacker/ability to respect) and/or a disruption TARGET and which Dossier role fits (fragile_preevo = low-HP pre-evo of the wincon; prize_liability = ex/Mega-ex; engine = consistency Pokémon; or "no"); and concretely how we neutralize it (gust / snipe / disrupt / out-tempo / play around) — objective, deck-neutral. Cross-check every claim against the engine FACTS and report any conflict in facts_conflict. Cite sources.`,
      { phase: 'Cards', schema: CARD_SCHEMA, label: `card:${c.name}`, effort: 'medium' }))),
])

// ── Round 2 — deep-read swept sources, then adversarially verify each claim (pipeline: a URL's claims
// verify as soon as its read finishes; no barrier between read and verify) ──
const candUrls = []
const seenUrl = new Set()
for (const s of swept.filter(Boolean)) {
  for (const u of (s.urls || [])) {
    if (u && u.url && !seenUrl.has(u.url)) { seenUrl.add(u.url); candUrls.push(u) }
  }
}
log(`${candUrls.length} candidate sources from the sweep`)

const verifiedClaims = (await pipeline(
  candUrls.slice(0, 12),
  u => agent(
    `${TCG}\n\nDeep-read this page for the ${ARCH} deck. WebFetch: ${u.url}\n(title: ${u.title})\n\nFirst decide whether the page is actually about THIS archetype/cards (matching the FACTS above) versus an older/different deck — set about_this_deck. Then extract concrete, actionable claims about how it wins, its tempo, its weaknesses, how it's countered, its threats, and matchups. Only extract claims relevant to this deck.`,
    { phase: 'Read', schema: READ_SCHEMA, label: 'read', effort: 'low' }),
  (read) => {
    if (!read || read.about_this_deck === 'no') return []
    return parallel((read.claims || []).map(c => () =>
      agent(
        `${TCG}\n\nAdversarially verify this claim about the ${ARCH} deck against the engine FACTS above. Default to skepticism.\n\nCLAIM (topic ${c.topic}, source ${read.url}): ${c.claim}\n\nVerdict:\n- supported = consistent with the FACTS and with plausible competitive reasoning\n- contradicts_facts = conflicts with the actual card text/costs/HP in the FACTS\n- about_different_deck = the claim is really about a different card/era/deck\n- unverifiable = cannot tell. Give a one-line note.`,
        { phase: 'Verify', schema: VERIFY_SCHEMA, label: `verify:${c.topic}`, effort: 'low' })
        .then(v => v ? { ...c, ...v, url: read.url } : null)))
  }
)).filter(Boolean).flat().filter(Boolean)

const good = verifiedClaims.filter(v => v.verdict === 'supported')
log(`${good.length}/${verifiedClaims.length} claims survived adversarial verification`)

// ── Synthesis — objective counterplay doctrine; lean on verified claims + per-card findings ──
const cards = (cardFindings || []).filter(Boolean)
const conflicts = cards
  .filter(x => x.facts_conflict && x.facts_conflict.toLowerCase() !== 'none')
  .map(x => `${x.card}: ${x.facts_conflict}`)

const synthesis = await agent(
  `Synthesize an OBJECTIVE counterplay doctrine for beating the ${ARCH} Pokemon TCG deck, for an author who will turn it into a shared Matchup Brief (deck-neutral — do NOT tailor it to any one of our decks).\n\nHow it wins (confirmed by the user):\n${GAMEPLAN}\n\nGround-truth engine FACTS (authoritative — NEVER contradict these; the simulator overrides every web guide):\n${FACTS}\n\nVERIFIED claims (survived adversarial check):\n${JSON.stringify(good, null, 1)}\n\nPER-KEY-CARD findings (function / threat / target role / how to neutralize):\n${JSON.stringify(cards, null, 1)}\n\nWeb-vs-FACTS conflicts surfaced (call these out):\n${conflicts.length ? conflicts.join('\n') : '(none reported)'}\n\nProduce: how_it_wins; tempo (fast/midrange/slow); weaknesses (each a seam + an objective exploit); threats (attackers to respect, card + why); targets (what to disrupt/snipe, card + Dossier role fragile_preevo|prize_liability|engine + why — only cards actually in this deck); counter_lines (concrete objective lines that beat it); gaps; sources; confidence. Lean ONLY on verified/sourced claims — if web coverage is thin (these sets can be bleeding-edge), say so under gaps and keep confidence honest. Do NOT invent lines. Cite the source URLs actually used.`,
  { phase: 'Synthesize', schema: SYNTH_SCHEMA, effort: 'high' })

return {
  synthesis,
  conflicts,
  stats: {
    angles: swept.filter(Boolean).length,
    sources: candUrls.length,
    claims_verified: good.length,
    claims_total: verifiedClaims.length,
    key_cards_covered: cards.length,
  },
}
