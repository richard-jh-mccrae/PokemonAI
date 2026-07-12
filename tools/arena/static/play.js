/* Arena match board. Dumb renderer of the server-built view (see tools/arena/view.py).
   All server-derived strings go through textContent — never innerHTML. */
'use strict';
(() => {
  const $ = (id) => document.getElementById(id);
  const boardEl = $('board');
  const tickerEl = $('ticker');
  const historyList = $('history-list');
  const handEl = $('hand');
  const promptEl = $('prompt');
  const optionsEl = $('options');
  const confirmRow = $('confirm-row');
  const confirmBtn = $('confirm-btn');
  const skipBtn = $('skip-btn');

  const EVENT_MS = 500;      // pacing between ticker lines
  const DRAIN_CAP_MS = 3000; // a whole batch never delays the prompt longer than this
  const HISTORY_CAP = 30;
  const KIND = { YES: 1, NO: 2, RETREAT: 12, ATTACK: 13, END: 14 };
  const COND_BADGE = { poisoned: 'PSN', burned: 'BRN', asleep: 'SLP', paralyzed: 'PAR', confused: 'CNF' };
  // EnergyType ints (src/cg/api.py) -> Limitless letter + name; colors are .pip.e<N> in play.css
  const ENERGY = {
    0: ['C', 'Colorless'], 1: ['G', 'Grass'], 2: ['R', 'Fire'], 3: ['W', 'Water'],
    4: ['L', 'Lightning'], 5: ['P', 'Psychic'], 6: ['F', 'Fighting'], 7: ['D', 'Darkness'],
    8: ['M', 'Metal'], 9: ['N', 'Dragon'], 10: ['✶', 'Rainbow'], 11: ['TR', 'Team Rocket'],
  };

  const params = new URLSearchParams(location.search);
  const tableId = params.get('table');
  const vsName = params.get('vs');
  if (vsName) $('vs').textContent = 'vs ' + vsName;

  let ws = null;
  let ended = false;          // end overlay shown; ignore socket close after this
  let busy = true;            // true while waiting on the server (no inputs)
  let view = null;            // last rendered view
  let select = null;          // current view.select
  let selectedIdx = new Set();   // multi-select staging
  let eventQueue = [];
  let pendingView = null;     // view withheld until its events finish ticking
  let pendingEnd = null;      // end message withheld the same way
  let draining = false;

  // --- banner -----------------------------------------------------------------

  function showBanner(text, withDeckLink) {
    const b = $('banner');
    b.textContent = text;
    if (withDeckLink) {
      b.appendChild(document.createTextNode(' '));
      const a = document.createElement('a');
      a.href = 'deck.html';
      a.textContent = 'Pick a deck';
      b.appendChild(a);
    }
    b.hidden = false;
  }

  if (!tableId) {
    showBanner('No table.', true);
    promptEl.textContent = '';
    return;
  }

  // --- socket -----------------------------------------------------------------

  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(proto + '://' + location.host + '/ws/' + encodeURIComponent(tableId));
  // the engine + agent boot takes a few seconds — say so, or the page reads as dead
  promptEl.textContent = 'Setting up the match — shuffling decks…';
  ws.onmessage = (e) => {
    let msg;
    try { msg = JSON.parse(e.data); } catch { return; }
    if (msg.type === 'state') onState(msg.view || {});
    else if (msg.type === 'end') onEnd(msg);
    else if (msg.type === 'thinking') setThinking();            // reconnect mid-bot-turn
    else if (msg.type === 'error') {
      ended = true;
      showBanner('Table not found — start a new game.', true);
    }
  };
  ws.onclose = (e) => {
    if (ended) return;
    if (e.code === 4404) showBanner('Table not found — start a new game.', true);
    else showBanner('Connection lost — reload to rejoin your match.');
  };

  function sendChoice(indices) {
    if (busy || ended || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: 'choose', indices }));
    setThinking();
  }

  $('concede').addEventListener('click', () => {
    if (ended || !ws || ws.readyState !== WebSocket.OPEN) return;
    if (confirm('Concede the match?')) ws.send(JSON.stringify({ type: 'concede' }));
  });

  // --- event pacing -------------------------------------------------------------
  // New events tick out one at a time BEFORE the new prompt/options appear.

  function onState(v) {
    const events = v.events || [];
    if (events.length) eventQueue.push(...events);
    pendingView = v;
    if (!draining) drainStep();
  }

  function onEnd(msg) {
    pendingEnd = msg;
    if (!draining) drainStep();
  }

  function drainStep() {
    if (eventQueue.length) {
      draining = true;
      showTick(eventQueue.shift());
      // long batches (setup draws) speed up so the whole drain fits the cap
      const pace = Math.min(EVENT_MS, DRAIN_CAP_MS / (eventQueue.length + 1));
      setTimeout(drainStep, pace);
      return;
    }
    draining = false;
    if (pendingView) { const v = pendingView; pendingView = null; render(v); }
    if (pendingEnd) { const m = pendingEnd; pendingEnd = null; showEnd(m); }
  }

  function showTick(text) {
    tickerEl.classList.remove('tick');
    void tickerEl.offsetWidth;         // restart the animation
    tickerEl.textContent = text;
    tickerEl.classList.add('tick');
    const li = document.createElement('li');
    li.textContent = text;
    historyList.appendChild(li);
    while (historyList.children.length > HISTORY_CAP) historyList.removeChild(historyList.firstChild);
  }

  // --- board rendering ------------------------------------------------------------

  function monCard(mon, opts) {
    // opts: {zone, index, opp, big, conditions}
    const el = document.createElement('div');
    el.className = 'mon' + (opts.big ? ' active-mon' : '');
    el.dataset.zone = opts.zone;
    el.dataset.index = String(opts.index);
    el.dataset.opp = opts.opp ? '1' : '0';

    if (!mon) {                       // face-down opponent active
      el.classList.add('face-down');
      el.textContent = '?';
      return el;
    }
    if (mon.id != null) {             // card scan as the face; 404 → text-only fallback
      const art = document.createElement('img');
      art.className = 'mon-art';
      art.src = '/cards/' + mon.id + '.png';
      art.setAttribute('alt', '');    // decorative — the name renders right below
      art.draggable = false;
      art.addEventListener('error', () => art.remove());
      el.appendChild(art);
    }
    const name = document.createElement('div');
    name.className = 'mon-name';
    name.textContent = mon.name;
    el.appendChild(name);

    const bar = document.createElement('div');
    const pct = mon.max_hp ? Math.max(0, Math.min(1, mon.hp / mon.max_hp)) : 0;
    bar.className = 'hp-bar' + (pct < 0.3 ? ' hp-low' : pct < 0.6 ? ' hp-mid' : '');
    const fill = document.createElement('div');
    fill.style.width = (pct * 100).toFixed(0) + '%';
    bar.appendChild(fill);
    el.appendChild(bar);

    const meta = document.createElement('div');
    meta.className = 'mon-meta';
    meta.textContent = (mon.hp ?? '?') + '/' + (mon.max_hp ?? '?');
    el.appendChild(meta);

    const energies = mon.energies || [];
    if (energies.length) {                 // typed pips — one per attached energy unit
      const row = document.createElement('div');
      row.className = 'energy-row';
      const MAX_PIPS = 6;
      for (const t of energies.slice(0, MAX_PIPS)) {
        const [letter, name] = ENERGY[t] || ['?', 'Unknown'];
        const pip = document.createElement('span');
        pip.className = 'pip e' + t;
        pip.textContent = letter;
        pip.title = name + ' energy';
        row.appendChild(pip);
      }
      if (energies.length > MAX_PIPS) {
        const more = document.createElement('span');
        more.className = 'pip pip-more';
        more.textContent = '+' + (energies.length - MAX_PIPS);
        more.title = energies.length + ' energy attached';
        row.appendChild(more);
      }
      el.appendChild(row);
    }

    if (mon.tools && mon.tools.length) {
      const tools = document.createElement('div');
      tools.className = 'tools';
      tools.textContent = mon.tools.join(' · ');
      el.appendChild(tools);
    }
    for (const c of opts.conditions || []) {
      const b = document.createElement('span');
      b.className = 'badge';
      b.title = c;
      b.textContent = COND_BADGE[c] || c;
      el.appendChild(b);
    }
    return el;
  }

  function renderSide(side, opp) {
    const p = opp ? 'opp' : 'you';
    const statsEl = $(p + '-stats');
    const activeEl = $(p + '-active');
    const benchEl = $(p + '-bench');
    activeEl.textContent = '';
    benchEl.textContent = '';
    if (!side) { statsEl.textContent = ''; return; }

    // hand + deck are counts only (tournament-visible info); the discard is public,
    // so its count opens the pile viewer
    statsEl.textContent = '';
    const bits = [];
    if (opp) bits.push('Hand ' + (side.hand_count ?? 0));
    bits.push('Deck ' + (side.deck_count ?? 0));
    bits.push('Prizes ' + (side.prizes ?? 0));
    statsEl.appendChild(document.createTextNode(bits.join(' · ') + ' · '));
    const discard = side.discard || [];
    const pileBtn = document.createElement('button');
    pileBtn.type = 'button';
    pileBtn.className = 'pile-btn';
    pileBtn.textContent = 'Discard ' + discard.length;
    pileBtn.disabled = !discard.length;
    pileBtn.addEventListener('click', (e) => { e.stopPropagation(); openPile(opp ? 'opp' : 'you'); });
    statsEl.appendChild(pileBtn);

    activeEl.appendChild(monCard(side.active, {
      zone: 'active', index: 0, opp, big: true, conditions: side.conditions,
    }));
    (side.bench || []).forEach((m, i) => {
      benchEl.appendChild(monCard(m, { zone: 'bench', index: i, opp }));
    });
  }

  function renderHand(hand) {
    handEl.textContent = '';
    for (const card of hand || []) {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chip';
      chip.dataset.handIndex = String(card.i);
      if (card.id != null) {          // mini card image; 404 → plain text pill
        chip.classList.add('card-chip');
        const img = document.createElement('img');
        img.className = 'chip-img';
        img.src = '/cards/' + card.id + '.png';
        img.setAttribute('alt', card.name);
        img.draggable = false;
        img.addEventListener('error', () => {
          img.remove();
          chip.classList.remove('card-chip');
        });
        chip.appendChild(img);
      }
      const cap = document.createElement('span');
      cap.className = 'chip-name';
      cap.textContent = card.name;
      chip.appendChild(cap);
      chip.addEventListener('pointerdown', (e) => armDrag(e, card.i, chip));
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        if (dragJustEnded) return;         // that "click" was a drop
        onHandTap(card.i, chip);
      });
      handEl.appendChild(chip);
    }
  }

  // --- options panel -------------------------------------------------------------

  function renderOptions() {
    optionsEl.textContent = '';
    selectedIdx = new Set();
    clearStaging();
    if (!select) {
      confirmRow.hidden = true;
      return;
    }
    const multi = (select.max || 1) > 1;
    for (const opt of select.options || []) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'opt';
      if (opt.kind === KIND.ATTACK) b.classList.add('kind-attack');
      if (opt.kind === KIND.END) b.classList.add('kind-end');
      if (opt.kind === KIND.YES || opt.kind === KIND.NO) b.classList.add('kind-yesno');
      b.dataset.i = String(opt.i);
      b.textContent = opt.label;
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        if (busy) return;
        if (multi) toggleOption(opt.i, b);
        else sendChoice([opt.i]);
      });
      optionsEl.appendChild(b);
    }
    const showSkip = (select.min || 0) === 0 && (select.options || []).length > 0;
    skipBtn.hidden = !showSkip;
    confirmBtn.hidden = !multi;
    confirmRow.hidden = !(multi || showSkip);
    if (multi) updateConfirm();
  }

  function toggleOption(i, btn) {
    if (selectedIdx.has(i)) { selectedIdx.delete(i); btn.classList.remove('selected'); }
    else if (selectedIdx.size < (select.max || 1)) { selectedIdx.add(i); btn.classList.add('selected'); }
    updateConfirm();
  }

  function updateConfirm() {
    const n = selectedIdx.size;
    confirmBtn.textContent = n ? 'Confirm (' + n + ')' : 'Confirm';
    confirmBtn.disabled = busy || n < (select.min || 0) || n > (select.max || 1);
  }

  confirmBtn.addEventListener('click', () => {
    if (busy || !select) return;
    const n = selectedIdx.size;
    if (n < (select.min || 0) || n > (select.max || 1)) return;
    sendChoice([...selectedIdx].sort((a, b) => a - b));
  });

  skipBtn.addEventListener('click', () => { if (!busy) sendChoice([]); });

  // --- tap-the-board sugar ----------------------------------------------------------
  // Hand chip → the options sourced from that card; one match acts immediately,
  // several matches highlight their board targets.

  function findMon(t) {
    return boardEl.querySelector(
      '.mon[data-zone="' + t.zone + '"][data-index="' + (t.index ?? 0) + '"][data-opp="' + (t.opp ? '1' : '0') + '"]');
  }

  function handMatches(handIndex) {
    return (select.options || []).filter(
      (o) => o.source && o.source.zone === 'hand' && o.source.index === handIndex);
  }

  function onHandTap(handIndex, chip) {
    if (busy || !select) return;
    clearStaging();
    const matches = handMatches(handIndex);
    if (!matches.length) return;
    if (matches.length === 1) { resolveOption(matches[0]); return; }

    chip.classList.add('staged');
    let highlighted = 0;
    for (const opt of matches) {
      const t = opt.target;
      if (!t || (t.zone !== 'active' && t.zone !== 'bench')) continue;
      const el = findMon(t);
      if (el) {
        el.classList.add('highlight');
        el.dataset.optI = String(opt.i);
        highlighted++;
      }
    }
    if (!highlighted) chip.classList.remove('staged');   // no board targets — use the panel
  }

  // Options that ARE a board pick (a target with no hand source — snipe targets,
  // promotions, heal picks) light up on the board itself; tapping the Pokémon picks it.
  function clearPicks() {
    for (const el of boardEl.querySelectorAll('.mon.pickable')) {
      el.classList.remove('pickable');
      delete el.dataset.pickI;
    }
  }

  function markBoardPicks() {
    clearPicks();
    if (!select) return;
    for (const opt of select.options || []) {
      if (opt.source || !opt.target) continue;
      const t = opt.target;
      if (t.zone !== 'active' && t.zone !== 'bench') continue;
      const el = findMon(t);
      if (el && el.dataset.pickI == null) {
        el.classList.add('pickable');
        el.dataset.pickI = String(opt.i);
      }
    }
  }

  boardEl.addEventListener('click', (e) => {
    if (busy || !select) return;
    const staged = e.target.closest('.mon.highlight');
    const mon = staged || e.target.closest('.mon.pickable');
    if (!mon) return;
    e.stopPropagation();
    const i = Number(staged ? mon.dataset.optI : mon.dataset.pickI);
    const opt = (select.options || []).find((o) => o.i === i);
    clearStaging();
    if (opt) resolveOption(opt);
  });

  document.addEventListener('click', () => clearStaging());   // tap elsewhere cancels

  function resolveOption(opt) {
    if ((select.max || 1) > 1) {
      const btn = optionsEl.querySelector('.opt[data-i="' + opt.i + '"]');
      if (btn) toggleOption(opt.i, btn);
    } else {
      sendChoice([opt.i]);
    }
  }

  function clearStaging() {
    for (const el of boardEl.querySelectorAll('.mon.highlight')) {
      el.classList.remove('highlight');
      delete el.dataset.optI;
    }
    for (const c of handEl.querySelectorAll('.chip.staged')) c.classList.remove('staged');
  }

  // --- drag a hand card onto the board ------------------------------------------------
  // Pointer-based, so touch and mouse both work. A drag resolves to the SAME option a
  // tap would: drop on a lit-up Pokémon for targeted options (attach/evolve), drop
  // anywhere on your side for untargeted ones (play a card, bench picks). Chips keep
  // touch-action: pan-x, so sideways swipes still scroll the hand natively — a mostly
  // vertical pull is what starts a drag.

  let drag = null;            // {chip, id, matches, ghost, started, x0, y0, sideOpt, dropEl}
  let dragJustEnded = false;  // swallow the click event that follows a real drag

  function armDrag(e, handIndex, chip) {
    if (busy || ended || !select || drag || !e.isPrimary || chip.disabled) return;
    const matches = handMatches(handIndex);
    if (!matches.length) return;
    drag = { chip, id: e.pointerId, matches, ghost: null,
             x0: e.clientX, y0: e.clientY, started: false, sideOpt: null, dropEl: null };
    try { chip.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
    chip.addEventListener('pointermove', moveDrag);
    chip.addEventListener('pointerup', endDrag);
    chip.addEventListener('pointercancel', cancelDrag);
  }

  function startDrag(e) {
    drag.started = true;
    clearStaging();
    document.body.classList.add('dragging');
    drag.chip.classList.add('drag-src');
    const ghost = drag.chip.cloneNode(true);
    ghost.className = 'chip drag-ghost' + (drag.chip.classList.contains('card-chip') ? ' card-chip' : '');
    ghost.disabled = true;
    document.body.appendChild(ghost);
    drag.ghost = ghost;
    for (const opt of drag.matches) {
      const t = opt.target;
      if (t && (t.zone === 'active' || t.zone === 'bench')) {
        const el = findMon(t);
        if (el) { el.classList.add('highlight'); el.dataset.optI = String(opt.i); }
      } else if (!t && !drag.sideOpt) {
        drag.sideOpt = opt;                          // play it / pick it from hand
      }
    }
    if (drag.sideOpt) $('you-side').classList.add('drop-zone');
    moveGhost(e);
  }

  function moveGhost(e) {
    drag.ghost.style.left = e.clientX + 'px';
    drag.ghost.style.top = e.clientY + 'px';
  }

  function dropTargetAt(x, y) {
    const under = document.elementFromPoint(x, y);   // the ghost is pointer-events: none
    if (!under) return null;
    const mon = under.closest('.mon.highlight');
    if (mon) return mon;
    if (drag.sideOpt && under.closest('#you-side')) return $('you-side');
    return null;
  }

  function moveDrag(e) {
    if (!drag || e.pointerId !== drag.id) return;
    if (!drag.started) {
      const dx = e.clientX - drag.x0, dy = e.clientY - drag.y0;
      if (Math.hypot(dx, dy) < 8) return;
      // touch: sideways pulls belong to the hand's native scroll (pointercancel follows)
      if (e.pointerType !== 'mouse' && Math.abs(dx) > Math.abs(dy)) return;
      startDrag(e);
    }
    moveGhost(e);
    const target = dropTargetAt(e.clientX, e.clientY);
    if (target !== drag.dropEl) {
      if (drag.dropEl) drag.dropEl.classList.remove('drop-hover');
      drag.dropEl = target;
      if (target) target.classList.add('drop-hover');
    }
  }

  function endDrag(e) {
    if (!drag || e.pointerId !== drag.id) return;
    const wasStarted = drag.started;
    const target = wasStarted ? dropTargetAt(e.clientX, e.clientY) : null;
    let opt = null;
    if (target === $('you-side')) opt = drag.sideOpt;
    else if (target) opt = (select.options || []).find((o) => o.i === Number(target.dataset.optI));
    cleanupDrag();
    if (wasStarted) {
      dragJustEnded = true;
      setTimeout(() => { dragJustEnded = false; }, 0);
      if (opt && !busy) resolveOption(opt);
    }
  }

  function cancelDrag(e) {
    if (!drag || e.pointerId !== drag.id) return;
    cleanupDrag();
  }

  function cleanupDrag() {
    const d = drag;
    drag = null;
    if (!d) return;
    d.chip.removeEventListener('pointermove', moveDrag);
    d.chip.removeEventListener('pointerup', endDrag);
    d.chip.removeEventListener('pointercancel', cancelDrag);
    d.chip.classList.remove('drag-src');
    if (d.ghost) d.ghost.remove();
    if (d.dropEl) d.dropEl.classList.remove('drop-hover');
    $('you-side').classList.remove('drop-zone');
    document.body.classList.remove('dragging');
    if (d.started) clearStaging();                   // drop the drag highlights
  }

  // --- discard pile viewer --------------------------------------------------------
  // Both discards are public knowledge at a real table; hand + deck stay counts
  // (view.py never sends their contents).

  let openPileSide = null;    // 'you' | 'opp' while the overlay is up

  function openPile(side) {
    openPileSide = side;
    const owner = side === 'opp' ? view && view.opp : view && view.you;
    const cards = (owner && owner.discard) || [];
    $('pile-title').textContent =
      (side === 'opp' ? "Opponent's discard" : 'Your discard') + ' (' + cards.length + ')';
    const grid = $('pile-grid');
    grid.textContent = '';
    for (const card of cards) {
      const cell = document.createElement('div');
      cell.className = 'pile-cell';
      if (card.id != null) {              // card scan; 404 → name-only cell
        const img = document.createElement('img');
        img.src = '/cards/' + card.id + '.png';
        img.setAttribute('alt', '');
        img.draggable = false;
        img.addEventListener('error', () => img.remove());
        cell.appendChild(img);
      }
      const cap = document.createElement('div');
      cap.className = 'pile-name';
      cap.textContent = card.name;
      cell.appendChild(cap);
      grid.appendChild(cell);
    }
    if (!cards.length) {
      const empty = document.createElement('p');
      empty.className = 'muted';
      empty.textContent = 'Empty.';
      grid.appendChild(empty);
    }
    $('pile-overlay').hidden = false;
  }

  function closePile() {
    openPileSide = null;
    $('pile-overlay').hidden = true;
  }

  $('pile-close').addEventListener('click', closePile);
  $('pile-overlay').addEventListener('click', (e) => {
    if (e.target === $('pile-overlay')) closePile();
  });

  // --- pile carousel ---------------------------------------------------------------
  // Fetch/reveal selects (deck search, discard fetch, look-at-top) show the actual
  // cards in a scrollable strip instead of the text panel: mouse wheel or a sideways
  // drag moves one card at a time, the centered card is the candidate, tapping it
  // picks it (or stages it in an up-to-N select). Same option indices as the panel.

  const carEl = $('carousel');
  const carStrip = $('car-strip');
  const carViewport = $('car-viewport');
  const carCaption = $('car-caption');
  let car = null;             // {opts, idx} while a pile select is up
  let carWheelAcc = 0;
  let carDrag = null;         // {id, x0, dx, moved}
  let carSuppressClick = false;

  function carouselEligible() {
    const opts = (select && select.options) || [];
    return opts.length > 0 && opts.every((o) => o.card != null && o.pile);
  }

  function renderCarousel() {
    carWheelAcc = 0;
    carDrag = null;
    if (!carouselEligible()) {
      car = null;
      carEl.hidden = true;
      optionsEl.classList.remove('replaced');
      return;
    }
    car = { opts: select.options, idx: 0 };
    carStrip.textContent = '';
    for (const o of car.opts) {
      const cell = document.createElement('button');
      cell.type = 'button';
      cell.className = 'car-cell';
      cell.dataset.i = String(o.i);
      const img = document.createElement('img');
      img.src = '/cards/' + o.card + '.png';
      img.setAttribute('alt', '');
      img.draggable = false;
      img.addEventListener('error', () => { img.remove(); cell.classList.add('no-img'); });
      cell.appendChild(img);
      const nm = document.createElement('span');
      nm.className = 'car-name';
      nm.textContent = o.label;
      cell.appendChild(nm);
      cell.addEventListener('click', (e) => {
        e.stopPropagation();
        if (busy || !car || carSuppressClick) return;
        const pos = car.opts.indexOf(o);
        if (pos !== car.idx) { car.idx = pos; layoutCarousel(); return; }   // focus first
        resolveOption(o);
        if (car) layoutCarousel();                     // staged badge in up-to-N selects
      });
      carStrip.appendChild(cell);
    }
    carEl.hidden = false;
    optionsEl.classList.add('replaced');               // the panel yields to the cards
    layoutCarousel();
  }

  function layoutCarousel(dragPx) {
    if (!car) return;
    const cells = carStrip.children;
    if (!cells.length) return;
    const cellW = cells[0].offsetWidth;
    const gap = parseFloat(getComputedStyle(carStrip).columnGap) || 0;
    const stepW = cellW + gap;
    const base = carViewport.clientWidth / 2 - cellW / 2 - car.idx * stepW;
    carStrip.classList.toggle('no-anim', dragPx != null);
    carStrip.style.transform = 'translateX(' + (base + (dragPx || 0)) + 'px)';
    for (let p = 0; p < cells.length; p++) {
      const d = Math.abs(p - car.idx);
      cells[p].className = 'car-cell' +
        (cells[p].classList.contains('no-img') ? ' no-img' : '') +
        (d === 0 ? ' d0' : d === 1 ? ' d1' : d === 2 ? ' d2' : ' dfar') +
        (selectedIdx.has(car.opts[p].i) ? ' staged' : '');
    }
    const focused = car.opts[car.idx];
    const multi = !!select && (select.max || 1) > 1;
    carCaption.textContent = focused.label + (multi
      ? '  ·  ' + selectedIdx.size + '/' + (select.max || 1) + ' — tap to add or remove'
      : '  —  tap to take');
    $('car-prev').disabled = busy || car.idx === 0;
    $('car-next').disabled = busy || car.idx === car.opts.length - 1;
  }

  function carStep(delta) {
    if (busy || !car) return;
    const next = Math.max(0, Math.min(car.opts.length - 1, car.idx + delta));
    if (next === car.idx) return;
    car.idx = next;
    layoutCarousel();
  }

  $('car-prev').addEventListener('click', () => carStep(-1));
  $('car-next').addEventListener('click', () => carStep(1));

  carEl.addEventListener('wheel', (e) => {
    if (busy || !car) return;
    e.preventDefault();                                // the wheel drives the strip, not the page
    const delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
    carWheelAcc = Math.max(-120, Math.min(120, carWheelAcc + delta));
    while (carWheelAcc >= 50) { carStep(1); carWheelAcc -= 50; }
    while (carWheelAcc <= -50) { carStep(-1); carWheelAcc += 50; }
  }, { passive: false });

  carViewport.addEventListener('pointerdown', (e) => {
    if (busy || !car || !e.isPrimary) return;
    carDrag = { id: e.pointerId, x0: e.clientX, dx: 0, moved: false };
    try { carViewport.setPointerCapture(e.pointerId); } catch { /* pointer already gone */ }
  });
  carViewport.addEventListener('pointermove', (e) => {
    if (!carDrag || e.pointerId !== carDrag.id) return;
    carDrag.dx = e.clientX - carDrag.x0;
    if (!carDrag.moved && Math.abs(carDrag.dx) > 8) carDrag.moved = true;
    if (carDrag.moved) layoutCarousel(carDrag.dx);
  });
  const carDragEnd = (e) => {
    if (!carDrag || e.pointerId !== carDrag.id) return;
    const d = carDrag;
    carDrag = null;
    if (!d.moved || !car) return;
    carSuppressClick = true;                           // that pointerup is not a tap
    setTimeout(() => { carSuppressClick = false; }, 0);
    const cells = carStrip.children;
    const stepW = cells.length
      ? cells[0].offsetWidth + (parseFloat(getComputedStyle(carStrip).columnGap) || 0) : 1;
    car.idx = Math.max(0, Math.min(car.opts.length - 1, car.idx - Math.round(d.dx / stepW)));
    layoutCarousel();
  };
  carViewport.addEventListener('pointerup', carDragEnd);
  carViewport.addEventListener('pointercancel', carDragEnd);
  window.addEventListener('resize', () => { if (car) layoutCarousel(); });

  // --- top-level render ---------------------------------------------------------------

  function render(v) {
    view = v;
    select = v.select || null;
    if (v.phase === 'setup') {
      promptEl.classList.add('thinking');
      promptEl.textContent = 'Setting up the match…';
      return;
    }
    $('turn').textContent = v.turn != null ? 'Turn ' + v.turn : '';
    renderSide(v.opp, true);
    renderSide(v.you, false);
    renderHand(v.you && v.you.hand);
    renderOptions();
    renderCarousel();
    markBoardPicks();
    if (openPileSide) openPile(openPileSide);        // keep an open pile current
    if (select) {
      busy = false;
      promptEl.classList.remove('thinking');
      promptEl.textContent = select.prompt || 'Make a selection';
      if ((select.max || 1) > 1) updateConfirm();
    } else {
      busy = true;
      promptEl.classList.add('thinking');
      promptEl.textContent = v.phase === 'over' ? 'Match over' : 'Waiting for the bot…';
    }
  }

  function setThinking() {
    busy = true;
    clearStaging();
    clearPicks();
    promptEl.classList.add('thinking');
    promptEl.textContent = 'Bot is thinking…';
    for (const b of optionsEl.querySelectorAll('button')) b.disabled = true;
    for (const c of handEl.querySelectorAll('button')) c.disabled = true;
    for (const b of carEl.querySelectorAll('button')) b.disabled = true;
    confirmBtn.disabled = true;
    skipBtn.disabled = true;
  }

  // --- end overlay + rating ----------------------------------------------------------

  let phaseSel = null;

  function showEnd(msg) {
    ended = true;
    busy = true;
    clearStaging();
    closePile();
    if (msg.error) {                       // the worker died — no result, no replay to rate
      $('end-title').textContent = 'Match ended unexpectedly';
      $('end-note').textContent = 'Sorry — something broke on our side.';
      $('rating-form').hidden = true;
      $('overlay').hidden = false;
      return;
    }
    const title = msg.draw ? 'Draw' : msg.you_won ? 'You won! 🎉' : 'You lost';
    $('end-title').textContent = title;
    $('end-note').textContent =
      msg.forfeit === 'concede' ? '(conceded)' : msg.forfeit === 'timeout' ? '(timed out)' : '';
    $('overlay').hidden = false;
  }

  for (const b of document.querySelectorAll('#phase-seg button')) {
    b.addEventListener('click', () => {
      phaseSel = phaseSel === b.dataset.phase ? null : b.dataset.phase;   // deselectable
      for (const x of document.querySelectorAll('#phase-seg button')) {
        x.classList.toggle('selected', x.dataset.phase === phaseSel);
      }
    });
  }

  $('rating-submit').addEventListener('click', () => {
    const btn = $('rating-submit');
    btn.disabled = true;
    $('rating-error').textContent = '';
    fetch('/api/tables/' + encodeURIComponent(tableId) + '/rating', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        misplay: $('misplay').value.trim() || null,
        phase: phaseSel,
        comments: $('comments').value.trim() || null,
      }),
    })
      .then((r) => {
        if (!r.ok) throw new Error('rating rejected');
        showThanks();
      })
      .catch(() => {
        btn.disabled = false;
        $('rating-error').textContent = 'Could not send — try again, or skip.';
      });
  });

  $('rating-skip').addEventListener('click', (e) => {
    e.preventDefault();
    showThanks();
  });

  function showThanks() {
    $('rating-form').hidden = true;
    $('thanks').hidden = false;
  }
})();
