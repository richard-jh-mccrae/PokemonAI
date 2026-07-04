export const meta = {
  name: 'deck-genie-research',
  description: 'Deck-parameterized web research for a Pokemon TCG archetype: parallel archetype sweep + per-confusing-card deep dives + trainer-by-trainer purpose pass, adversarially verified against engine card facts, synthesized with citations. Driven entirely by `args` (deck/facts/gameplan/angles/confusing_cards/trainers) — never hardcode a deck here.',
  phases: [
    { title: 'Sweep', detail: 'parallel archetype web searches by angle' },
    { title: 'Cards', detail: 'one deep-dive agent per confusing/non-obvious card' },
    { title: 'Trainers', detail: 'one purpose agent per trainer card' },
    { title: 'Read', detail: 'deep-fetch the promising sources from the sweep' },
    { title: 'Verify', detail: 'adversarially check each claim against engine card facts' },
    { title: 'Synthesize', detail: 'cited synthesis + per-card purpose map + explicit gaps' },
  ],
}

// ── Inputs (all from `args`; the SKILL gathers these from the engine dump + Phase-1 overview) ──
// NOTE: the Workflow harness delivers a nested `args` object JSON-STRINGIFIED (typeof args === 'string'),
// so reading `args.deck` directly yields undefined and the whole sweep silently no-ops. Parse
// defensively — works whether args arrives as a string (current harness) or an object (contract).
let ARGV
try {
  ARGV = (typeof args === 'string') ? JSON.parse(args) : (args || {})
} catch (e) {
  throw new Error(`deck-genie-research: could not parse args (${String((e && e.message) || e)}). ` +
    `Invoke as Workflow({ scriptPath, args: { deck, gameplan, facts, angles:[...], confusing_cards:[...], trainers:[...] } }). ` +
    `Raw args prefix: ${String(args).slice(0, 200)}`)
}

const DECK = ARGV.deck || 'this deck'
const FACTS = ARGV.facts || '(no engine facts supplied — flag this as a gap)'
const GAMEPLAN = ARGV.gameplan || '(win condition not yet confirmed)'
const ANGLES = ARGV.angles || []                           // [{key, q}]
const CONFUSING = ARGV.confusing_cards || []               // [{name, why}]
const TRAINERS = ARGV.trainers || []                       // [{name, tags}] or ["name", ...]

// Fail LOUDLY rather than silently running an empty sweep (the args-binding bug's symptom:
// 0 angles · 0 cards · 0 sources · only the self-serving synth agent ran).
if (ANGLES.length === 0 && CONFUSING.length === 0 && TRAINERS.length === 0) {
  throw new Error(`deck-genie-research: no angles, confusing_cards, OR trainers after parsing args — ` +
    `refusing to run an empty sweep. typeof args=${typeof args}; parsed keys=${JSON.stringify(Object.keys(ARGV))}. ` +
    `Ensure the Workflow call passes args: { deck, gameplan, facts, angles:[...], confusing_cards:[...], trainers:[...] }.`)
}

// One shared preamble so every web agent knows the set is the physical/online TCG (NOT Pocket) and
// that the competition simulator's card facts OVERRIDE any web guide (Scarlet & Violet Mega era +
// simulator deltas — see CLAUDE.md / docs/rules.md). FACTS is the ground truth; the web is a prior.
const TCG = `You research the Pokemon Trading Card Game (the physical/online TCG — NOT Pokemon TCG Pocket, the mobile app). This is a competitive deck whose plan is:\n${GAMEPLAN}\n\nEngine-confirmed card facts for THIS deck (ground truth — the simulator's stats/costs/text OVERRIDE any web guide; use these to judge relevance and catch misreads):\n${FACTS}`

const SWEEP_SCHEMA = { type: 'object', additionalProperties: false, required: ['urls', 'notes'],
  properties: {
    urls: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['url', 'title', 'why'],
      properties: { url: { type: 'string' }, title: { type: 'string' }, why: { type: 'string' } } } },
    notes: { type: 'string' },
  } }

const CARD_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['card', 'purpose', 'companions', 'setup', 'when_played', 'anti_patterns', 'facts_conflict', 'sources', 'confidence'],
  properties: {
    card: { type: 'string' },
    purpose: { type: 'string', description: 'why this exact card is in this exact deck — its job' },
    companions: { type: 'array', items: { type: 'string' }, description: 'cards it combos with / sets up / is set up by' },
    setup: { type: 'string', description: 'what has to be true on board/hand for it to do its job' },
    when_played: { type: 'string', description: 'the turn/board state it is played on, and sequencing vs other cards' },
    anti_patterns: { type: 'array', items: { type: 'string' }, description: 'when NOT to play it / common misplays' },
    facts_conflict: { type: 'string', description: 'any web claim that conflicts with the engine FACTS, or "none"' },
    sources: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'url'],
      properties: { title: { type: 'string' }, url: { type: 'string' } } } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  } }

const TRAINER_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['card', 'purpose', 'priority', 'when_played', 'fetch_targets', 'facts_conflict', 'confidence'],
  properties: {
    card: { type: 'string' },
    purpose: { type: 'string', description: 'the specific reason this trainer is in this deck (not a generic blurb)' },
    priority: { type: 'string', description: 'for Supporters: where it sits in the once-per-turn priority order; for Items: where in the sequencing ladder' },
    when_played: { type: 'string' },
    fetch_targets: { type: 'array', items: { type: 'string' }, description: 'for search/draw cards: what to grab, in priority order (or [])' },
    facts_conflict: { type: 'string', description: 'web claim that conflicts with engine FACTS, or "none"' },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  } }

const READ_SCHEMA = { type: 'object', additionalProperties: false, required: ['url', 'about_our_deck', 'claims'],
  properties: {
    url: { type: 'string' },
    about_our_deck: { type: 'string', enum: ['yes', 'no', 'unsure'] },
    claims: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['topic', 'claim'],
      properties: { topic: { type: 'string', enum: ['gameplan', 'combo', 'sequencing', 'opening', 'matchup', 'tech', 'ratio', 'other'] },
        claim: { type: 'string' } } } },
  } }

const VERIFY_SCHEMA = { type: 'object', additionalProperties: false, required: ['verdict', 'note'],
  properties: { verdict: { type: 'string', enum: ['supported', 'contradicts_facts', 'about_different_card', 'unverifiable'] },
    note: { type: 'string' } } }

const SYNTH_SCHEMA = { type: 'object', additionalProperties: false,
  required: ['gameplan', 'combos', 'sequencing', 'opening_lines', 'matchups', 'tech_reasoning',
             'card_purposes', 'trainer_purposes', 'gaps', 'sources', 'confidence'],
  properties: {
    gameplan: { type: 'string' },
    combos: { type: 'array', items: { type: 'string' } },
    sequencing: { type: 'array', items: { type: 'string' } },
    opening_lines: { type: 'array', items: { type: 'string' } },
    matchups: { type: 'array', items: { type: 'string' } },
    tech_reasoning: { type: 'array', items: { type: 'string' } },
    card_purposes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['card', 'purpose'],
      properties: { card: { type: 'string' }, purpose: { type: 'string' } } } },
    trainer_purposes: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['card', 'purpose'],
      properties: { card: { type: 'string' }, purpose: { type: 'string' } } } },
    gaps: { type: 'array', items: { type: 'string' } },
    sources: { type: 'array', items: { type: 'object', additionalProperties: false, required: ['title', 'url'],
      properties: { title: { type: 'string' }, url: { type: 'string' } } } },
    confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
  } }

log(`researching ${DECK}: ${ANGLES.length} archetype angles · ${CONFUSING.length} deep-dive cards · ${TRAINERS.length} trainers`)

// ── Round 1 — fan everything out at once (shared concurrency pool) so wall-clock stays low ──
// Sweep finds sources; Cards and Trainers are self-contained (each searches+reads+returns findings,
// self-checking against FACTS). opts.phase tags each agent's group (global phase() would race here).
const [swept, cardFindings, trainerFindings] = await Promise.all([
  parallel(ANGLES.map(a => () =>
    agent(
      `${TCG}\n\nSEARCH ANGLE for the ${DECK} archetype: ${a.q}\n\nRun 2-4 web searches and open the most relevant results. Prefer recent competitive sources (deck guides, tournament reports, meta articles, ladder lists). Return the URLs worth a deep read (url + title + why relevant) and put anything immediately useful in notes. If web tools are unavailable, say so in notes.`,
      { phase: 'Sweep', schema: SWEEP_SCHEMA, label: `sweep:${a.key}`, effort: 'low' }))),

  parallel(CONFUSING.map(c => () =>
    agent(
      `${TCG}\n\nDEEP-DIVE one confusing/non-obvious card in the ${DECK} deck and figure out WHY it is there and HOW to use it. This card's inclusion is not self-evident:\n\nCARD: ${c.name}\nWHY IT'S CONFUSING: ${c.why || 'its role in this deck is non-obvious'}\n\nWeb-search this card BY NAME in the context of the ${DECK} deck (e.g. "${c.name} ${DECK} deck", "why ${c.name} in <archetype>"), open the best results, and pin down: its exact job, the companion cards it combos with / is set up by, the board/hand setup it needs, the turn & sequencing it's played on, and the common misplays. Cross-check every claim against the engine FACTS above and report any conflict in facts_conflict. Be concrete; cite sources.`,
      { phase: 'Cards', schema: CARD_SCHEMA, label: `card:${c.name}`, effort: 'medium' }))),

  parallel(TRAINERS.map(t => () => {
    const name = typeof t === 'string' ? t : t.name
    const tags = typeof t === 'string' ? '' : (t.tags ? ` (function tags: ${t.tags})` : '')
    return agent(
      `${TCG}\n\nPin down the PURPOSE of one trainer card in the ${DECK} deck — every trainer is in the list on purpose, so find its specific job (not a generic blurb).\n\nTRAINER: ${name}${tags}\n\nIf it's a generic staple (e.g. a standard Ball/draw Supporter) whose role is obvious, give the standard purpose tersely — no deep search needed. If its inclusion or count is deck-specific or unusual, web-search it in this deck's context and dig in. Pin down: why this deck runs it (and this count), its priority/sequencing (Supporters are once-per-turn — where in the order; Items — where in the turn's ladder), what it fetches/does in priority order, and when it's played. Cross-check against the engine FACTS and report any conflict in facts_conflict.`,
      { phase: 'Trainers', schema: TRAINER_SCHEMA, label: `trainer:${name}`, effort: 'low' })
  })),
])

// ── Round 2 — deep-read the swept sources, then adversarially verify each claim (pipeline: a URL's
// claims verify as soon as its read finishes; no barrier between read and verify) ──
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
    `${TCG}\n\nDeep-read this page for the ${DECK} deck. WebFetch: ${u.url}\n(title: ${u.title})\n\nFirst decide whether the page is actually about THIS archetype/cards (matching the FACTS above) versus an older/different deck — set about_our_deck. Then extract concrete, actionable strategy claims (gameplan, combos, sequencing, opening lines, matchups, tech choices, card ratios). Only extract claims relevant to our deck.`,
    { phase: 'Read', schema: READ_SCHEMA, label: 'read', effort: 'low' }),
  (read) => {
    if (!read || read.about_our_deck === 'no') return []
    return parallel((read.claims || []).map(c => () =>
      agent(
        `${TCG}\n\nAdversarially verify this strategy claim about the ${DECK} deck against the engine FACTS above. Default to skepticism.\n\nCLAIM (topic ${c.topic}, source ${read.url}): ${c.claim}\n\nVerdict:\n- supported = consistent with the FACTS and with plausible competitive reasoning\n- contradicts_facts = conflicts with the actual card text/costs/HP in the FACTS\n- about_different_card = the claim is really about a different card/era/deck\n- unverifiable = cannot tell. Give a one-line note.`,
        { phase: 'Verify', schema: VERIFY_SCHEMA, label: `verify:${c.topic}`, effort: 'low' })
        .then(v => v ? { ...c, ...v, url: read.url } : null)))
  }
)).filter(Boolean).flat().filter(Boolean)

const good = verifiedClaims.filter(v => v.verdict === 'supported')
log(`${good.length}/${verifiedClaims.length} archetype claims survived adversarial verification`)

// ── Synthesis — lean on verified claims + the per-card / per-trainer findings; keep gaps honest ──
const cards = (cardFindings || []).filter(Boolean)
const trainers = (trainerFindings || []).filter(Boolean)
const conflicts = [...cards, ...trainers]
  .filter(x => x.facts_conflict && x.facts_conflict.toLowerCase() !== 'none')
  .map(x => `${x.card}: ${x.facts_conflict}`)

const synthesis = await agent(
  `Synthesize a competitive playing doctrine for the ${DECK} Pokemon TCG deck, for an agent author who will turn it into Pilot rules.\n\nDeck plan (confirmed by the user):\n${GAMEPLAN}\n\nGround-truth engine FACTS (authoritative — NEVER contradict these; the simulator overrides every web guide):\n${FACTS}\n\nVERIFIED archetype claims (survived adversarial check):\n${JSON.stringify(good, null, 1)}\n\nPER-CONFUSING-CARD deep dives:\n${JSON.stringify(cards, null, 1)}\n\nPER-TRAINER purpose findings:\n${JSON.stringify(trainers, null, 1)}\n\nWeb-vs-FACTS conflicts surfaced during research (call these out explicitly):\n${conflicts.length ? conflicts.join('\n') : '(none reported)'}\n\nProduce a cited synthesis: gameplan; combos; sequencing ladder; opening lines; matchups; tech reasoning; a per-card purpose map (card_purposes) covering the confusing/non-obvious Pokémon; a per-trainer purpose map (trainer_purposes) covering EVERY trainer researched; gaps; sources; confidence. Lean ONLY on verified/sourced claims for assertions — if web coverage is thin (these sets can be bleeding-edge), say so under gaps and keep confidence honest. Do NOT invent lines. Cite the source URLs actually used.`,
  { phase: 'Synthesize', schema: SYNTH_SCHEMA, effort: 'high' })

return {
  synthesis,
  conflicts,
  stats: {
    angles: swept.filter(Boolean).length,
    sources: candUrls.length,
    claims_verified: good.length,
    claims_total: verifiedClaims.length,
    cards_deep_dived: cards.length,
    trainers_covered: trainers.length,
  },
}
