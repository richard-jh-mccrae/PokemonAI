/* Arena deck builder. Working deck lives in localStorage ('arena-build').
   All server-derived strings go through textContent — never innerHTML. */
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const titleEl = $('title');
  const countEl = $('count');
  const problemsEl = $('problems');
  const errEl = $('start-error');
  const startBtn = $('start');
  const searchEl = $('search');
  const sortEl = $('sort');
  const tabsEl = $('tabs');
  const chipsEl = $('chips');
  const poolListEl = $('pool-list');
  const poolMoreEl = $('pool-more');
  const poolMoreBtn = $('pool-more-btn');

  const LS_KEY = 'arena-build';
  const POOL_CAP = 60;                 // pool rows per page
  const GROUP = {
    pokemon: 'pokemon',
    item: 'trainer', tool: 'trainer', supporter: 'trainer', stadium: 'trainer',
    basic_energy: 'energy', special_energy: 'energy',
  };
  const STAGE_LABEL = { basic: 'Basic', stage1: 'Stage 1', stage2: 'Stage 2' };
  const CAT_LABEL = {
    pokemon: 'Pokémon', item: 'Item', tool: 'Tool', supporter: 'Supporter',
    stadium: 'Stadium', basic_energy: 'Basic Energy', special_energy: 'Special Energy',
  };

  const params = new URLSearchParams(location.search);
  const fromParam = params.get('from');
  const visitor = (params.get('visitor') || '').trim();

  let catalog = [];              // name-sorted card list
  let byId = new Map();          // id -> card
  let counts = new Map();        // id -> count in the working deck
  let deckTitle = 'New deck';
  let filter = 'all';
  let sortMode = 'name';         // 'name' | 'hp' | 'damage'
  let poolShown = POOL_CAP;      // rows currently paged in
  let sheetId = null;            // card id open in the detail sheet
  let starting = false;

  const activeChips = new Map(); // chip group id -> Set of active values
  const evolvesInto = new Map(); // card name -> sorted names evolving from it

  // --- deck math ---------------------------------------------------------------

  function total() {
    let t = 0;
    for (const n of counts.values()) t += n;
    return t;
  }

  function nameTotal(name) {     // copies across all ids sharing the name
    let t = 0;
    for (const [id, n] of counts) {
      const c = byId.get(id);
      if (c && c.name === name) t += n;
    }
    return t;
  }

  function aceTotal() {
    let t = 0;
    for (const [id, n] of counts) {
      const c = byId.get(id);
      if (c && c.aceSpec) t += n;
    }
    return t;
  }

  function hasBasicPokemon() {
    for (const [id, n] of counts) {
      const c = byId.get(id);
      if (n > 0 && c && c.category === 'pokemon' && c.stage === 'basic') return true;
    }
    return false;
  }

  function legalityProblems() {
    const p = [];
    const t = total();
    if (t > 60) p.push(t + ' cards — a deck is exactly 60');
    const seen = new Set();
    for (const id of counts.keys()) {
      const c = byId.get(id);
      if (!c || c.category === 'basic_energy' || seen.has(c.name)) continue;
      seen.add(c.name);
      if (nameTotal(c.name) > 4) p.push('more than 4 × ' + c.name);
    }
    if (aceTotal() > 1) p.push('more than 1 ACE SPEC');
    if (!hasBasicPokemon()) p.push('no Basic Pokémon');
    return p;
  }

  function canAdd(card) {
    if (!card || total() >= 60) return false;
    if (card.category !== 'basic_energy' && nameTotal(card.name) >= 4) return false;
    if (card.aceSpec && aceTotal() >= 1) return false;
    return true;
  }

  // --- persistence ----------------------------------------------------------------

  function save() {
    try {
      localStorage.setItem(LS_KEY,
        JSON.stringify({ title: deckTitle, counts: Object.fromEntries(counts) }));
    } catch { /* storage full/blocked — builder still works in memory */ }
  }

  function loadDraft() {
    let draft = null;
    try { draft = JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch { return false; }
    if (!draft || typeof draft !== 'object' || !draft.counts || typeof draft.counts !== 'object') {
      return false;
    }
    deckTitle = typeof draft.title === 'string' && draft.title ? draft.title : 'New deck';
    counts = new Map();
    for (const [k, v] of Object.entries(draft.counts)) {
      const id = Number(k);
      const n = Number(v);
      if (byId.has(id) && Number.isInteger(n) && n > 0) counts.set(id, Math.min(n, 60));
    }
    return true;
  }

  // --- mutations --------------------------------------------------------------------

  function add(id) {
    const c = byId.get(id);
    if (!canAdd(c)) return;
    counts.set(id, (counts.get(id) || 0) + 1);
    onChange();
  }

  function removeOne(id) {
    const n = counts.get(id) || 0;
    if (!n) return;
    if (n === 1) counts.delete(id);
    else counts.set(id, n - 1);
    onChange();
  }

  function onChange() {
    errEl.textContent = '';       // stale server verdicts clear on any edit
    save();
    renderAll();
  }

  // --- shared row bits -----------------------------------------------------------------

  function metaText(c) {
    if (c.category === 'pokemon') {
      const bits = [c.hp + ' HP', STAGE_LABEL[c.stage] || ''];
      if (c.megaEx) bits.push('Mega ex');
      else if (c.ex) bits.push('ex');
      return bits.filter(Boolean).join(' · ');
    }
    const bits = [CAT_LABEL[c.category] || c.category];
    if (c.aceSpec) bits.push('ACE SPEC');
    return bits.join(' · ');
  }

  function nameButton(c) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'row-name';
    if (c.img) {                         // server vouched the scan exists on this host
      const im = document.createElement('img');
      im.className = 'row-thumb';
      im.src = '/cards/' + c.id + '.png';
      im.setAttribute('alt', '');        // decorative — the name sits right beside it
      im.loading = 'lazy';
      im.draggable = false;
      im.addEventListener('error', () => im.remove());
      b.appendChild(im);
    }
    const txt = document.createElement('span');
    txt.className = 'row-text';
    const nm = document.createElement('span');
    nm.className = 'nm';
    nm.textContent = c.name;
    const meta = document.createElement('span');
    meta.className = 'row-meta';
    meta.textContent = metaText(c);
    txt.appendChild(nm);
    txt.appendChild(meta);
    b.appendChild(txt);
    b.addEventListener('click', () => openSheet(c.id));
    return b;
  }

  function stepBtn(label, ariaLabel, disabled, onTap) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'step';
    b.textContent = label;
    b.setAttribute('aria-label', ariaLabel);
    b.disabled = disabled;
    b.addEventListener('click', onTap);
    return b;
  }

  // --- deck pane ------------------------------------------------------------------------

  function deckRow(c, n) {
    const row = document.createElement('div');
    row.className = 'card-row';
    const cnt = document.createElement('span');
    cnt.className = 'row-count';
    cnt.textContent = n + '×';
    row.appendChild(cnt);
    row.appendChild(nameButton(c));
    const steps = document.createElement('div');
    steps.className = 'steppers';
    steps.appendChild(stepBtn('−', 'Remove one ' + c.name, false, () => removeOne(c.id)));
    steps.appendChild(stepBtn('+', 'Add one ' + c.name, !canAdd(c), () => add(c.id)));
    row.appendChild(steps);
    return row;
  }

  function renderDeck() {
    const groups = { pokemon: [], trainer: [], energy: [] };
    for (const [id, n] of counts) {
      const c = byId.get(id);
      if (c && n > 0) groups[GROUP[c.category] || 'trainer'].push({ c, n });
    }
    for (const g of ['pokemon', 'trainer', 'energy']) {
      groups[g].sort((a, b) => a.c.name.localeCompare(b.c.name) || a.c.id - b.c.id);
      const sec = $('sec-' + g);
      const rows = sec.querySelector('.deck-rows');
      rows.textContent = '';
      for (const { c, n } of groups[g]) rows.appendChild(deckRow(c, n));
      sec.hidden = !groups[g].length;
    }
    $('deck-empty').hidden = total() > 0;
  }

  // --- pool browser ------------------------------------------------------------------------

  const norm = (s) => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  // Chip groups per tab: chips OR within a group, groups AND together.
  const TYPES = ['grass', 'fire', 'water', 'lightning', 'psychic', 'fighting',
                 'darkness', 'metal', 'dragon', 'colorless'];
  const CHIP_GROUPS = {
    pokemon: [
      { id: 'stage',
        chips: [['Basic', 'basic'], ['Stage 1', 'stage1'], ['Stage 2', 'stage2']],
        test: (c, v) => c.stage === v },
      { id: 'type',
        chips: TYPES.map((t) => [cap(t), t]),
        test: (c, v) => c.energy === v },
      { id: 'flag',
        chips: [['ex', 'ex'], ['Mega', 'mega'], ['Ability', 'ability']],
        test: (c, v) => (v === 'ex' ? c.ex : v === 'mega' ? c.megaEx
                         : c.category === 'pokemon' && !!c.effect) },
    ],
    trainer: [
      { id: 'tcat',
        chips: [['Item', 'item'], ['Supporter', 'supporter'], ['Tool', 'tool'],
                ['Stadium', 'stadium']],
        test: (c, v) => c.category === v },
      { id: 'tflag',
        chips: [['ACE SPEC', 'ace']],
        test: (c) => c.aceSpec },
    ],
    energy: [
      { id: 'ecat',
        chips: [['Basic', 'basic_energy'], ['Special', 'special_energy']],
        test: (c, v) => c.category === v },
    ],
  };

  function renderChips() {
    chipsEl.textContent = '';
    const groups = CHIP_GROUPS[filter];
    chipsEl.hidden = !groups;
    if (!groups) return;
    groups.forEach((g, gi) => {
      if (gi) {
        const sep = document.createElement('span');
        sep.className = 'chip-sep';
        chipsEl.appendChild(sep);
      }
      for (const [label, v] of g.chips) {
        const sel = activeChips.get(g.id);
        const on = !!sel && sel.has(v);
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip' + (on ? ' staged' : '');
        b.setAttribute('aria-pressed', String(on));
        b.textContent = label;
        b.addEventListener('click', () => toggleChip(g.id, v));
        chipsEl.appendChild(b);
      }
    });
  }

  function toggleChip(group, v) {
    let s = activeChips.get(group);
    if (!s) { s = new Set(); activeChips.set(group, s); }
    if (s.has(v)) s.delete(v); else s.add(v);
    if (!s.size) activeChips.delete(group);
    poolShown = POOL_CAP;
    renderChips();
    renderPool();
  }

  function chipPass(c) {
    const groups = CHIP_GROUPS[filter];
    if (!groups) return true;
    for (const g of groups) {
      const sel = activeChips.get(g.id);
      if (!sel || !sel.size) continue;
      let ok = false;
      for (const v of sel) if (g.test(c, v)) { ok = true; break; }
      if (!ok) return false;
    }
    return true;
  }

  function maxDamage(c) {
    let d = 0;
    for (const a of c.attacks || []) {
      const n = Number(a.damage) || 0;
      if (n > d) d = n;
    }
    return d;
  }

  function sortCards(arr) {
    if (sortMode === 'name') return;       // catalog order is already name-sorted
    const key = sortMode === 'hp'
      ? (c) => (c.category === 'pokemon' ? c.hp : -1)
      : (c) => (c.category === 'pokemon' ? maxDamage(c) : -1);
    arr.sort((a, b) => key(b) - key(a)
      || a.name.localeCompare(b.name) || a.id - b.id);
  }

  function poolMatches() {
    const q = norm(searchEl.value.trim());
    const nameHits = [];
    const textHits = [];                   // matched only in attack/effect text
    for (const c of catalog) {
      if (filter !== 'all' && GROUP[c.category] !== filter) continue;
      if (!chipPass(c)) continue;
      if (!q || c.searchName.includes(q)) nameHits.push(c);
      else if (c.searchText.includes(q)) textHits.push(c);
    }
    sortCards(nameHits);
    sortCards(textHits);
    return nameHits.concat(textHits);
  }

  function poolRow(c) {
    const row = document.createElement('div');
    row.className = 'card-row';
    row.appendChild(nameButton(c));
    const n = counts.get(c.id) || 0;
    if (n) {
      const badge = document.createElement('span');
      badge.className = 'in-deck';
      badge.textContent = String(n);
      row.appendChild(badge);
    }
    const steps = document.createElement('div');
    steps.className = 'steppers';
    steps.appendChild(stepBtn('+', 'Add one ' + c.name, !canAdd(c), () => add(c.id)));
    row.appendChild(steps);
    return row;
  }

  function renderPool() {
    poolListEl.textContent = '';
    const m = poolMatches();
    const shown = m.slice(0, poolShown);
    for (const c of shown) poolListEl.appendChild(poolRow(c));
    if (!m.length) {
      poolMoreEl.textContent = 'No matching cards.';
      poolMoreEl.hidden = false;
      poolMoreBtn.hidden = true;
    } else if (m.length > shown.length) {
      const left = m.length - shown.length;
      poolMoreEl.textContent = 'Showing ' + shown.length + ' of ' + m.length + ' cards';
      poolMoreEl.hidden = false;
      poolMoreBtn.textContent = 'Show ' + Math.min(POOL_CAP, left) + ' more (' + left + ' left)';
      poolMoreBtn.hidden = false;
    } else {
      poolMoreEl.hidden = true;
      poolMoreBtn.hidden = true;
    }
  }

  poolMoreBtn.addEventListener('click', () => {
    poolShown += POOL_CAP;
    renderPool();
  });

  searchEl.addEventListener('input', () => {
    poolShown = POOL_CAP;
    renderPool();
  });

  sortEl.addEventListener('change', () => {
    sortMode = sortEl.value;
    poolShown = POOL_CAP;
    renderPool();
  });

  tabsEl.addEventListener('click', (e) => {
    const b = e.target.closest('button[data-f]');
    if (!b) return;
    filter = b.dataset.f;
    for (const x of tabsEl.querySelectorAll('button')) {
      x.classList.toggle('selected', x === b);
    }
    activeChips.clear();                   // tab switch resets chips
    poolShown = POOL_CAP;
    renderChips();
    renderPool();
  });

  // --- detail sheet --------------------------------------------------------------------------

  function sheetLabel(text) {
    const d = document.createElement('div');
    d.className = 'sheet-label';
    d.textContent = text;
    return d;
  }

  function jumpToName(name) {              // evo-link tap: reset filters, search exact name
    closeSheet();
    filter = 'all';
    for (const x of tabsEl.querySelectorAll('button')) {
      x.classList.toggle('selected', x.dataset.f === 'all');
    }
    activeChips.clear();
    searchEl.value = name;
    poolShown = POOL_CAP;
    renderChips();
    renderPool();
    searchEl.scrollIntoView({ block: 'center' });
  }

  function evoLinks(label, names) {
    const frag = document.createDocumentFragment();
    frag.appendChild(sheetLabel(label));
    const p = document.createElement('p');
    p.className = 'sheet-effect';
    names.forEach((nm, i) => {
      if (i) p.appendChild(document.createTextNode(', '));
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'evo-link';
      b.textContent = nm;
      b.addEventListener('click', () => jumpToName(nm));
      p.appendChild(b);
    });
    frag.appendChild(p);
    return frag;
  }

  function openSheet(id) {
    const c = byId.get(id);
    if (!c) return;
    sheetId = id;
    $('s-name').textContent = c.name;
    const sub = [CAT_LABEL[c.category] || c.category];
    if (c.category === 'pokemon') {
      sub.push(STAGE_LABEL[c.stage] || '');
      if (c.megaEx) sub.push('Mega ex');
      else if (c.ex) sub.push('ex');
      if (c.energy) sub.push(c.energy.charAt(0).toUpperCase() + c.energy.slice(1));
    }
    if (c.aceSpec) sub.push('ACE SPEC');
    $('s-sub').textContent = sub.filter(Boolean).join(' · ');

    const body = $('s-body');
    body.textContent = '';
    if (c.img) {                          // scan up top; the text below stays the source of truth
      const im = document.createElement('img');
      im.className = 'sheet-img';
      im.src = '/cards/' + c.id + '.png';
      im.setAttribute('alt', '');
      im.draggable = false;
      im.addEventListener('error', () => im.remove());
      body.appendChild(im);
    }
    if (c.category === 'pokemon') {
      const stats = document.createElement('div');
      stats.className = 'sheet-stats';
      stats.textContent = c.hp + ' HP · Retreat ' + c.retreat;
      body.appendChild(stats);
    }
    for (const a of c.attacks || []) {
      const atk = document.createElement('div');
      atk.className = 'atk';
      const head = document.createElement('div');
      head.className = 'atk-head';
      const nm = document.createElement('span');
      nm.className = 'atk-name';
      nm.textContent = a.name || '';
      head.appendChild(nm);
      if (a.damage) {
        const dmg = document.createElement('span');
        dmg.className = 'atk-dmg';
        dmg.textContent = String(a.damage);
        head.appendChild(dmg);
      }
      atk.appendChild(head);
      const cost = document.createElement('div');
      cost.className = 'atk-cost';
      cost.textContent = (a.cost || []).length ? a.cost.join(' · ') : 'No cost';
      atk.appendChild(cost);
      if (a.text) {
        const t = document.createElement('p');
        t.className = 'atk-text';
        t.textContent = a.text;
        atk.appendChild(t);
      }
      body.appendChild(atk);
    }
    if (c.effect) {
      body.appendChild(sheetLabel(c.category === 'pokemon' ? 'Ability' : 'Effect'));
      const eff = document.createElement('p');
      eff.className = 'sheet-effect';
      eff.textContent = c.effect;
      body.appendChild(eff);
    }
    if (c.evolvesFrom) body.appendChild(evoLinks('Evolves from', [c.evolvesFrom]));
    const into = evolvesInto.get(c.name);
    if (into && into.length) body.appendChild(evoLinks('Evolves into', into));
    updateSheetFoot();
    $('sheet-wrap').hidden = false;
  }

  function updateSheetFoot() {
    if (sheetId == null) return;
    const c = byId.get(sheetId);
    const n = counts.get(sheetId) || 0;
    $('s-count').textContent = String(n);
    $('s-minus').disabled = !n;
    $('s-plus').disabled = !canAdd(c);
  }

  function closeSheet() {
    sheetId = null;
    $('sheet-wrap').hidden = true;
  }

  $('sheet-close').addEventListener('click', closeSheet);
  $('sheet-backdrop').addEventListener('click', closeSheet);
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && sheetId != null) closeSheet();
  });
  $('s-minus').addEventListener('click', () => { if (sheetId != null) removeOne(sheetId); });
  $('s-plus').addEventListener('click', () => { if (sheetId != null) add(sheetId); });

  // --- header + start ------------------------------------------------------------------------

  function renderHeader() {
    titleEl.textContent = deckTitle;
    const t = total();
    const probs = legalityProblems();
    const legal = t === 60 && !probs.length;
    countEl.textContent = t + '/60';
    countEl.classList.toggle('ok', legal);
    countEl.classList.toggle('warn', !legal);
    problemsEl.textContent = probs.join(' · ');
    startBtn.disabled = starting || !legal;
  }

  function renderAll() {
    renderHeader();
    renderDeck();
    renderPool();
    updateSheetFoot();
  }

  function errLine(text) {
    const s = document.createElement('span');
    s.textContent = text;
    return s;
  }

  startBtn.addEventListener('click', () => {
    if (starting) return;
    const t = total();
    if (t !== 60 || legalityProblems().length) return;
    const ids = [];
    for (const [id, n] of counts) for (let i = 0; i < n; i++) ids.push(id);
    ids.sort((a, b) => a - b);
    errEl.textContent = '';
    starting = true;
    startBtn.textContent = 'Starting…';
    renderHeader();
    const body = { deck_ids: ids };
    if (visitor) body.visitor = visitor;
    fetch('/api/tables', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(async (r) => {
        const data = await r.json().catch(() => ({}));
        if (r.ok && data.table_id) {
          location = 'play.html?table=' + encodeURIComponent(data.table_id)
                   + '&vs=' + encodeURIComponent(data.agent || '');
          return;
        }
        if (r.status === 400 && data.problems) {
          for (const p of data.problems) errEl.appendChild(errLine(p));
        } else {
          errEl.textContent = data.error || 'Could not start the match — try again.';
        }
        resetStart();
      })
      .catch(() => {
        errEl.textContent = 'Could not reach the server — try again.';
        resetStart();
      });
  });

  function resetStart() {
    starting = false;
    startBtn.textContent = 'Start';
    renderHeader();
  }

  $('clear').addEventListener('click', () => {
    counts = new Map();
    try { localStorage.removeItem(LS_KEY); } catch { /* ignore */ }
    errEl.textContent = '';
    renderAll();
  });

  // --- boot -----------------------------------------------------------------------------------

  function seed() {
    if (fromParam === 'empty') {          // explicit fresh start overrides any draft
      deckTitle = 'New deck';
      counts = new Map();
      save();
      return Promise.resolve();
    }
    if (fromParam) {                      // preset overrides any draft
      return fetch('/api/presets/' + encodeURIComponent(fromParam))
        .then((r) => { if (!r.ok) throw new Error('preset'); return r.json(); })
        .then((p) => {
          deckTitle = 'Editing: ' + (p.title || fromParam);
          counts = new Map();
          for (const e of p.cards || []) {
            const id = Number(e.id);
            const n = Number(e.count);
            if (byId.has(id) && Number.isInteger(n) && n > 0) counts.set(id, n);
          }
          save();
        })
        .catch(() => {
          deckTitle = 'New deck';
          counts = new Map();
          errEl.textContent = 'Could not load that preset — starting blank.';
        });
    }
    loadDraft();                          // no from param: restore the draft if present
    return Promise.resolve();
  }

  fetch('/api/cards')
    .then((r) => { if (!r.ok) throw new Error('cards'); return r.json(); })
    .then((data) => {
      catalog = data.cards || [];
      for (const c of catalog) {
        byId.set(c.id, c);
        c.searchName = norm(c.name);       // client-only fields; never rendered
        const bits = [];
        for (const a of c.attacks || []) {
          if (a.name) bits.push(a.name);
          if (a.text) bits.push(a.text);
        }
        if (c.effect) bits.push(c.effect);
        c.searchText = norm(bits.join('\n'));
        if (c.category === 'pokemon' && c.evolvesFrom) {
          let s = evolvesInto.get(c.evolvesFrom);
          if (!s) { s = new Set(); evolvesInto.set(c.evolvesFrom, s); }
          s.add(c.name);
        }
      }
      for (const [k, s] of evolvesInto) {
        evolvesInto.set(k, [...s].sort((a, b) => a.localeCompare(b)));
      }
      catalog.sort((a, b) => a.name.localeCompare(b.name) || a.id - b.id);
      return seed();
    })
    .then(() => {
      sortMode = sortEl.value || 'name';   // browsers may restore the select on reload
      renderChips();
      renderAll();
    })
    .catch(() => {
      titleEl.textContent = 'Deck builder';
      problemsEl.textContent = '';
      errEl.textContent = 'Could not load the card pool — reload to retry.';
    });
})();
