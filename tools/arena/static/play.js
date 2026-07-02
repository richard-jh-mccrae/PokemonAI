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
    meta.textContent = (mon.hp ?? '?') + '/' + (mon.max_hp ?? '?') +
      (mon.energy ? '  ⚡×' + mon.energy : '');
    el.appendChild(meta);

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

    const bits = [];
    if (opp) bits.push('Hand ' + (side.hand_count ?? 0));
    bits.push('Deck ' + (side.deck_count ?? 0));
    bits.push('Prizes ' + (side.prizes ?? 0));
    bits.push('Discard ' + ((side.discard || []).length));
    statsEl.textContent = bits.join(' · ');

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
      chip.addEventListener('click', (e) => { e.stopPropagation(); onHandTap(card.i, chip); });
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

  function onHandTap(handIndex, chip) {
    if (busy || !select) return;
    clearStaging();
    const matches = (select.options || []).filter(
      (o) => o.source && o.source.zone === 'hand' && o.source.index === handIndex);
    if (!matches.length) return;
    if (matches.length === 1) { resolveOption(matches[0]); return; }

    chip.classList.add('staged');
    let highlighted = 0;
    for (const opt of matches) {
      const t = opt.target;
      if (!t || (t.zone !== 'active' && t.zone !== 'bench')) continue;
      const el = boardEl.querySelector(
        '.mon[data-zone="' + t.zone + '"][data-index="' + (t.index ?? 0) + '"][data-opp="' + (t.opp ? '1' : '0') + '"]');
      if (el) {
        el.classList.add('highlight');
        el.dataset.optI = String(opt.i);
        highlighted++;
      }
    }
    if (!highlighted) chip.classList.remove('staged');   // no board targets — use the panel
  }

  boardEl.addEventListener('click', (e) => {
    const mon = e.target.closest('.mon.highlight');
    if (!mon || busy || !select) return;
    e.stopPropagation();
    const i = Number(mon.dataset.optI);
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
    promptEl.classList.add('thinking');
    promptEl.textContent = 'Bot is thinking…';
    for (const b of optionsEl.querySelectorAll('button')) b.disabled = true;
    for (const c of handEl.querySelectorAll('button')) c.disabled = true;
    confirmBtn.disabled = true;
    skipBtn.disabled = true;
  }

  // --- end overlay + rating ----------------------------------------------------------

  let phaseSel = null;

  function showEnd(msg) {
    ended = true;
    busy = true;
    clearStaging();
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
