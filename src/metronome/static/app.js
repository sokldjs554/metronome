/* Metronome dashboard: plain JS + inline SVG, no external dependencies.
   Five steps (data -> models -> deploy -> monitor -> policy); every button calls the real API. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const fmt = (x, d = 4) => (x === null || x === undefined || Number.isNaN(x)) ? '—' : Number(x).toFixed(d);
  const fmtInt = (x) => (x === null || x === undefined) ? '—' : Number(x).toLocaleString();
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const versionColor = (v) => {
    const n = parseInt(String(v).replace(/\D/g, ''), 10) || 0;
    return `var(--v${(n - 1 + 6) % 6})`;
  };
  const state = { auto: null, apiKey: null, evidence: null, replay: null, profile: null, models: null, dataset: null, fcChannel: null };

  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-store' });
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.json();
  }
  async function postJSON(url, body) {
    const headers = { 'content-type': 'application/json' };
    if (state.apiKey) headers['x-api-key'] = state.apiKey;
    const r = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body || {}) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) {
      const err = new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `${url}: ${r.status}`);
      err.status = r.status; err.data = data;
      throw err;
    }
    return data;
  }
  // Protected routes ask for the API key once (METRONOME_API_KEY), then retry.
  async function withKey(fn) {
    try { return await fn(); } catch (err) {
      if (err.status === 401 || /API key/.test(err.message)) {
        state.apiKey = window.prompt('API key (METRONOME_API_KEY)') || null;
        if (state.apiKey) return fn();
      }
      throw err;
    }
  }

  // ---- tabs ---------------------------------------------------------------------------------
  function showPanel(name) {
    document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.id === `panel-${name}`));
    document.querySelectorAll('.step').forEach((b) => b.classList.toggle('active', b.dataset.panel === name));
    if (history.replaceState) history.replaceState(null, '', `#${name}`);
    if (name === 'deploy' && !$('chart-forecast').childElementCount) runForecast().catch(() => {});
  }
  document.querySelectorAll('.step').forEach((b) => b.addEventListener('click', () => showPanel(b.dataset.panel)));

  // ---- SVG helpers --------------------------------------------------------------------------
  const SVG = 'http://www.w3.org/2000/svg';
  function el(tag, attrs, text) {
    const e = document.createElementNS(SVG, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function clear(svg) { while (svg.firstChild) svg.removeChild(svg.firstChild); }
  function scale(domain, range) {
    const [d0, d1] = domain, [r0, r1] = range;
    const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
    return (x) => r0 + (x - d0) * k;
  }
  function axes(svg, W, H, pad, x, y, xdom, ydom, xfmt, yfmt) {
    svg.appendChild(el('line', { x1: pad.l, x2: W - pad.r, y1: H - pad.b, y2: H - pad.b, class: 'axis' }));
    svg.appendChild(el('line', { x1: pad.l, x2: pad.l, y1: pad.t, y2: H - pad.b, class: 'axis' }));
    for (let i = 0; i <= 4; i++) {
      const yv = ydom[0] + (ydom[1] - ydom[0]) * i / 4;
      svg.appendChild(el('line', { x1: pad.l, x2: W - pad.r, y1: y(yv), y2: y(yv), class: 'axis', 'stroke-dasharray': '2 4' }));
      svg.appendChild(el('text', { x: pad.l - 6, y: y(yv) + 3, class: 'tick', 'text-anchor': 'end' }, yfmt(yv)));
    }
    for (let i = 0; i <= 4; i++) {
      const xv = xdom[0] + (xdom[1] - xdom[0]) * i / 4;
      svg.appendChild(el('text', { x: x(xv), y: H - pad.b + 14, class: 'tick', 'text-anchor': 'middle' }, xfmt(xv)));
    }
  }
  function polyline(svg, pts, attrs) {
    svg.appendChild(el('polyline', Object.assign({ points: pts.map(([a, b]) => `${a},${b}`).join(' '), class: 'series' }, attrs)));
  }

  // ---- 1 · data -----------------------------------------------------------------------------
  function kv(container, rows) {
    container.innerHTML = '';
    rows.forEach(([k, v, html]) => {
      const dt = document.createElement('dt'); dt.textContent = k;
      const dd = document.createElement('dd'); if (html) dd.innerHTML = v; else dd.textContent = v;
      container.append(dt, dd);
    });
  }
  function renderProfile(p) {
    state.profile = p;
    state.dataset = p.dataset;
    const src = p.source || {};
    const spec = p.spec || {};
    kv($('dataset-kv'), [
      ['데이터셋', `${p.dataset} (${spec.description || '공개 벤치마크'})`],
      ['원본', src.url ? `<a href="${esc(src.url)}" target="_blank" rel="noopener">${esc(src.url.replace(/^https?:\/\//, '').slice(0, 60))}…</a>` : '—', true],
      ['원본 SHA-256', src.sha256 ? `${src.sha256.slice(0, 16)}…` : '—'],
      ['처리본 해시', p.content_sha256 ? `${p.content_sha256.slice(0, 16)}…` : '—'],
      ['주기 · 채널', `${p.freq} · ${p.channels.length}개 (${p.channels.join(', ')})`],
      ['기간', `${(p.start || '').slice(0, 16)} ~ ${(p.end || '').slice(0, 16)} (${fmtInt(p.n_rows)}행)`],
      ['분할', `초기 학습 ${p.split.initial_days}일 (${fmtInt(p.split.initial_rows)}행) → 스트림 ${p.split.stream_days}일 (${fmtInt(p.split.stream_rows)}행), 시작 ${(p.split.stream_start_time || '').slice(0, 16)}`],
      ['모델 입출력', `lookback ${p.lookback} → horizon ${p.horizon}`],
      ['보간한 행', p.filled_rows === null || p.filled_rows === undefined ? '—' : fmtInt(p.filled_rows)],
    ]);
    const v = p.validation || {};
    const checks = [
      ['중복 시각', v.duplicates], ['역행 시각', v.non_monotonic], [`${p.freq} 보다 큰 간격`, v.gaps],
      ['NaN 셀', v.nan_cells], ['비유한 셀', v.non_finite_cells], ['상수 채널', (v.constant_channels || []).length],
    ];
    const tb = $('validation-table').querySelector('tbody');
    tb.innerHTML = '';
    if (!p.validation) { tb.innerHTML = '<tr><td colspan="3" class="muted">검사 보고서가 레지스트리에 없습니다(구 버전 배포).</td></tr>'; }
    checks.forEach(([name, n]) => {
      if (n === undefined) return;
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${name}</td><td class="num">${fmtInt(n)}</td><td class="${n ? 'state-alarm' : 'state-ok'}">${n ? '확인 필요' : '통과'}</td>`;
      tb.appendChild(tr);
    });
    const ct = $('channel-table').querySelector('tbody');
    ct.innerHTML = '';
    p.channel_stats.forEach((s, i) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><span class="swatch" style="background:var(--v${i % 6})"></span>${esc(s.name)}</td><td class="num">${fmt(s.mean, 2)}</td><td class="num">${fmt(s.std, 2)}</td><td class="num">${fmt(s.min, 2)}</td><td class="num">${fmt(s.max, 2)}</td><td class="num">${fmtInt(s.missing)}</td>`;
      ct.appendChild(tr);
    });
    drawSparklines(p);
    const sel = $('fc-channel');
    if (!sel.childElementCount) {
      p.channels.forEach((c, i) => { const o = document.createElement('option'); o.value = i; o.textContent = c; sel.appendChild(o); });
      sel.value = p.channels.length - 1; // the last channel is the target in ETT (oil temperature)
    }
  }
  function drawSparklines(p) {
    const svg = $('chart-spark');
    clear(svg);
    const W = 640, H = 220, pad = { l: 36, r: 12, t: 10, b: 24 };
    const rows = p.sparklines.values, n = rows.length;
    if (n < 2) return;
    const x = scale([0, n - 1], [pad.l, W - pad.r]);
    const y = scale([0, 1], [H - pad.b, pad.t]);
    axes(svg, W, H, pad, x, y, [0, n - 1], [0, 1], (i) => (p.sparklines.timestamps[Math.round(i)] || '').slice(0, 7), (v) => v.toFixed(1));
    p.channels.forEach((c, ci) => {
      const col = rows.map((r) => r[ci]);
      const lo = Math.min(...col), hi = Math.max(...col), span = hi - lo || 1;
      polyline(svg, col.map((v, i) => [x(i), y((v - lo) / span)]), { stroke: `var(--v${ci % 6})`, 'stroke-width': 1.5, opacity: 0.9 });
    });
    const splitFrac = p.split.initial_rows / p.n_rows;
    const sx = x(splitFrac * (n - 1));
    svg.appendChild(el('line', { x1: sx, x2: sx, y1: pad.t, y2: H - pad.b, stroke: 'var(--muted)', 'stroke-dasharray': '6 4' }));
    svg.appendChild(el('text', { x: sx + 4, y: pad.t + 10, class: 'tick' }, '스트림 시작'));
  }

  $('upload-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const f = $('upload-file').files[0];
    if (!f) return;
    const out = $('upload-result');
    out.className = ''; out.textContent = '검사 중…';
    const fd = new FormData();
    fd.append('file', f);
    fd.append('freq', $('upload-freq').value || '1h');
    try {
      const r = await fetch('/v1/data/validate', { method: 'POST', body: fd });
      const d = await r.json();
      if (!r.ok) { out.innerHTML = `<span class="badge bad">거부</span> ${esc(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail))}`; return; }
      renderUpload(d);
    } catch (err) { out.textContent = `오류: ${err.message}`; }
  });
  function renderUpload(d) {
    const rep = d.report;
    const out = $('upload-result');
    const checks = [['행', rep.n_rows], ['채널', rep.n_channels], ['중복 시각', rep.duplicates], ['역행 시각', rep.non_monotonic], [`${d.freq} 보다 큰 간격`, rep.gaps], ['NaN 셀', rep.nan_cells], ['상수 채널', rep.constant_channels.length], ['못 읽은 시각', d.bad_timestamps], ['버린 문자열 열', d.dropped_columns.length]];
    const head = `<p><span class="badge ${d.ok ? 'ok' : 'bad'}">${d.ok ? '통과' : '문제 있음'}</span> <b>${esc(d.filename)}</b> (${(d.bytes / 1024).toFixed(1)} KB) · 시각 열 <code>${esc(d.timestamp_column)}</code> · ${esc(rep.start.slice(0, 16))} ~ ${esc(rep.end.slice(0, 16))} · 학습에 필요한 최소 행 ${fmtInt(d.enough_history.needed_rows)} <span class="${d.enough_history.ok ? 'state-ok' : 'state-alarm'}">(${d.enough_history.ok ? '충분' : '부족'})</span></p>`;
    const probs = rep.problems.length ? `<ul class="problems">${rep.problems.map((p) => `<li>${esc(p)}</li>`).join('')}</ul>` : '<p class="state-ok">검사 항목 모두 통과. 이 파일로 레지스트리를 만들 수 있습니다.</p>';
    const table = `<table><thead><tr>${checks.map(([k]) => `<th class="num">${k}</th>`).join('')}</tr></thead><tbody><tr>${checks.map(([, v]) => `<td class="num">${fmtInt(v)}</td>`).join('')}</tr></tbody></table>`;
    const cols = ['timestamp', ...rep.channels.slice(0, 6)];
    const preview = `<table class="preview"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join('')}${rep.channels.length > 6 ? '<th>…</th>' : ''}</tr></thead><tbody>${d.preview.map((r) => `<tr>${cols.map((c) => `<td>${esc(c === 'timestamp' ? String(r[c]).slice(0, 19) : fmt(r[c], 3))}</td>`).join('')}${rep.channels.length > 6 ? '<td>…</td>' : ''}</tr>`).join('')}</tbody></table>`;
    out.innerHTML = head + probs + table + '<h3>앞 5행</h3>' + preview;
  }
  $('btn-sample').addEventListener('click', () => {
    // a small CSV with the problems the checker looks for, so the result is not just "pass"
    const rows = ['timestamp,load,temp'];
    const t0 = Date.UTC(2024, 0, 1);
    for (let h = 0; h < 72; h++) {
      if (h === 30) continue; // gap
      const ts = new Date(t0 + h * 3600e3).toISOString().slice(0, 19).replace('T', ' ');
      const load = (50 + 10 * Math.sin(2 * Math.PI * h / 24)).toFixed(2);
      rows.push(`${ts},${load},${h === 40 ? '' : (20 + h / 24).toFixed(2)}`);
      if (h === 10) rows.push(`${ts},${load},20.1`); // duplicate
    }
    const blob = new Blob([rows.join('\n') + '\n'], { type: 'text/csv' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'metronome-sample.csv'; a.click();
  });

  // ---- 2 · models ---------------------------------------------------------------------------
  function renderLeaderboard(lb) {
    $('leaderboard-note').textContent = lb.offline_note || '';
    const tb = $('leaderboard-table').querySelector('tbody');
    tb.innerHTML = '';
    const rows = lb.offline || [];
    if (!rows.length) tb.innerHTML = `<tr><td colspan="7" class="muted">${esc(lb.dataset)} 에는 오프라인 비교 실행이 없습니다.</td></tr>`;
    rows.forEach((r) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${esc(r.model)}</td><td class="num">${fmt(r.mse, 4)}</td><td class="num">${fmt(r.mae, 4)}</td><td class="num">${fmtInt(r.n_parameters)}</td><td class="num">${r.epochs === null ? '—' : fmt(r.epochs, 0)}</td><td class="num">${r.train_seconds === null ? '—' : fmt(r.train_seconds, 0)}</td><td class="num">${r.n_seeds}</td>`;
      tb.appendChild(tr);
    });
    const svg = $('chart-leaderboard');
    clear(svg);
    if (!rows.length) return;
    const W = 640, H = 200, pad = { l: 110, r: 50, t: 10, b: 10 };
    const bh = Math.min(24, (H - pad.t - pad.b) / rows.length);
    const xmax = Math.max(...rows.map((r) => r.mse));
    const x = scale([0, xmax], [pad.l, W - pad.r]);
    rows.forEach((r, i) => {
      const y0 = pad.t + i * bh;
      svg.appendChild(el('rect', { x: pad.l, y: y0 + 3, width: Math.max(1, x(r.mse) - pad.l), height: bh - 6, fill: /naive/.test(r.model) ? 'var(--muted)' : 'var(--accent)', rx: 3 }));
      svg.appendChild(el('text', { x: pad.l - 8, y: y0 + bh / 2 + 4, class: 'tick', 'text-anchor': 'end', 'font-size': 12 }, r.model));
      svg.appendChild(el('text', { x: x(r.mse) + 6, y: y0 + bh / 2 + 4, class: 'tick', 'font-size': 11 }, r.mse.toFixed(3)));
    });
  }
  function renderCandidates(c) {
    const ch = c.champion || {};
    kv($('champion-kv'), [
      ['현재 모델', ch.version || '—'],
      ['배포 시 검증 MAE', fmt(ch.val_mae_fixed, 4)],
      ['최근 7일 MAE (리플레이)', fmt(ch.rolling_7d_mae, 4)],
      ['게이트 기준', ch.rolling_7d_mae ? '최근 7일 MAE' : '배포 시 검증 MAE'],
    ]);
    const tb = $('candidates-table').querySelector('tbody');
    tb.innerHTML = '';
    const jobs = (c.jobs || []).slice(-8).reverse();
    if (!jobs.length) tb.innerHTML = '<tr><td colspan="8" class="muted">아직 작업이 없습니다. 계열을 고르고 후보 학습을 눌러 보세요.</td></tr>';
    jobs.forEach((j) => {
      const tr = document.createElement('tr');
      const st = { requested: '대기', training: '학습 중…', done: '등록됨', failed: '실패' }[j.status] || j.status;
      const gate = j.status !== 'done' ? '—' : j.active ? '<span class="badge ok">서비스 중</span>' : j.better_than_active === null ? '—' : j.better_than_active ? '<span class="state-ok">더 좋음</span>' : '<span class="state-alarm">더 나쁨</span>';
      const act = j.status === 'done' && !j.active ? `<button class="small" data-promote="${esc(j.version)}">게이트 승격</button> <button class="small secondary" data-force="${esc(j.version)}">강제</button>` : '';
      const trig = { candidate: '후보', detector: '검출기', schedule: '주기', initial: '초기' }[j.trigger] || j.trigger || '';
      tr.innerHTML = `<td title="${esc(j.job)}">${esc(trig)}</td><td>${esc(j.model || '—')}</td><td class="${j.status === 'failed' ? 'state-alarm' : ''}" title="${esc(j.error || '')}">${esc(st)}</td><td>${esc(j.version || '—')}</td><td class="num">${fmt(j.metrics && j.metrics.val_mae_fixed, 4)}</td><td class="num">${j.metrics && j.metrics.train_seconds !== null ? fmt(j.metrics.train_seconds, 1) : '—'}</td><td>${gate}</td><td>${act}</td>`;
      tb.appendChild(tr);
    });
    tb.querySelectorAll('[data-promote]').forEach((b) => b.addEventListener('click', () => promote(b.dataset.promote, false)));
    tb.querySelectorAll('[data-force]').forEach((b) => b.addEventListener('click', () => promote(b.dataset.force, true)));
    $('btn-candidate').disabled = (c.open_jobs || []).length > 0;
    if ((c.open_jobs || []).length) $('cand-status').textContent = 'worker 가 학습 중입니다…';
  }
  async function promote(version, force) {
    try {
      const r = await withKey(() => postJSON('/v1/candidates/promote', { version, force }));
      $('cand-status').textContent = `${r.candidate} 승격: 후보 ${fmt(r.candidate_val_mae, 4)} < 현재 ${fmt(r.champion_mae, 4)} (${r.champion_mae_source})`;
    } catch (err) {
      const d = err.data || {};
      $('cand-status').textContent = d.promote === false ? `게이트 거부: 후보 ${fmt(d.candidate_val_mae, 4)} ≥ 현재 ${fmt(d.champion_mae, 4)} (${d.champion_mae_source}). 강제로 올릴 수는 있습니다.` : `오류: ${err.message}`;
    }
    refresh();
  }
  $('btn-candidate').addEventListener('click', async () => {
    const model = $('cand-model').value, max_epochs = parseInt($('cand-epochs').value, 10) || 5;
    $('cand-status').textContent = '요청 중…';
    try {
      const r = await withKey(() => postJSON('/v1/candidates', { model, max_epochs }));
      $('cand-status').textContent = `작업 ${r.job} 등록. worker 가 ${model} 을 스트림 ${r.cutoff_time ? r.cutoff_time.slice(0, 13) : '끝'} 시점까지로 학습합니다.`;
    } catch (err) { $('cand-status').textContent = `오류: ${err.message}`; }
    refresh();
  });

  // ---- 3 · deploy ---------------------------------------------------------------------------
  function renderModel(models) {
    state.models = models;
    const a = models.active;
    kv($('model-kv'), a ? [
      ['버전', a.version], ['등록', a.created_at || '—'],
      ['계열 · 계기', `${(a.provenance && a.provenance.model) || '—'} · ${(a.provenance && a.provenance.trigger) || '—'}`],
      ['검증 MAE (고정 척도)', fmt(a.metrics && a.metrics.val_mae_fixed)],
      ['ONNX parity 편차', a.parity_max_abs_diff === undefined ? '—' : Number(a.parity_max_abs_diff).toExponential(2)],
      ['학습 데이터', a.provenance && a.provenance.cutoff_time ? `… ${a.provenance.cutoff_time.slice(0, 16)}` : '—'],
      ['ONNX SHA-256', a.onnx_sha256 ? a.onnx_sha256.slice(0, 16) + '…' : '—'],
      ['등록된 버전 수', String(models.versions.length)],
    ] : [['상태', models.load_error || '활성 모델 없음']]);
    $('chip-version').textContent = a ? `모델 ${a.version}` : '모델 없음';
    $('chip-version').style.color = a ? versionColor(a.version) : '';
    $('link-card').href = a ? `/v1/models/${a.version}/card` : '#';
    const tb = $('versions-table').querySelector('tbody');
    tb.innerHTML = '';
    models.versions.slice().reverse().forEach((v) => {
      const tr = document.createElement('tr');
      const active = a && v.version === a.version;
      const trig = { candidate: '후보', detector: '검출기', schedule: '주기', initial: '초기' }[v.provenance.trigger] || v.provenance.trigger || '';
      tr.innerHTML = `<td style="color:${versionColor(v.version)}"><b>${esc(v.version)}</b>${active ? ' <span class="badge ok">서비스 중</span>' : ''}</td><td>${esc(v.provenance.model || '—')}</td><td>${esc(trig)}</td><td class="num">${fmt(v.metrics.val_mae_fixed)}</td><td class="num">${v.metrics.export_parity_max_abs_diff === undefined ? '—' : Number(v.metrics.export_parity_max_abs_diff).toExponential(1)}</td><td>${esc((v.created_at || '').slice(5, 16).replace('T', ' '))}</td><td>${active ? '' : `<button class="small" data-activate="${esc(v.version)}">활성화</button>`} <a class="small-link" href="/v1/models/${esc(v.version)}/card" target="_blank" rel="noopener">카드</a></td>`;
      tb.appendChild(tr);
    });
    tb.querySelectorAll('[data-activate]').forEach((b) => b.addEventListener('click', async () => {
      try { await withKey(() => postJSON(`/v1/models/${b.dataset.activate}/activate?reason=dashboard`)); } catch (err) { window.alert(`거부: ${err.message}`); }
      refresh();
    }));
  }
  $('btn-rollback').addEventListener('click', async () => {
    try {
      const r = await withKey(() => postJSON('/v1/models/rollback'));
      $('fc-status').textContent = `${r.rolled_back_to} 로 되돌렸습니다 (parity ${Number(r.parity_max_abs_diff).toExponential(1)}).`;
    } catch (err) { window.alert(err.message); }
    refresh();
  });
  function renderEvents(events) {
    const ol = $('swap-events');
    ol.innerHTML = '';
    const swaps = events.swaps.slice(-6).reverse();
    if (!swaps.length) ol.innerHTML = '<li class="muted">아직 교체가 없습니다.</li>';
    swaps.forEach((e) => {
      const li = document.createElement('li');
      li.textContent = `${new Date(e.at * 1000).toLocaleTimeString()} ${e.from || '∅'} → ${e.to} (${e.reason})`;
      ol.appendChild(li);
    });
    const rl = $('retrain-events');
    rl.innerHTML = '';
    const reqs = events.retrain_requests.slice(-6).reverse();
    if (!reqs.length) rl.innerHTML = '<li class="muted">재학습 요청이 없습니다.</li>';
    reqs.forEach((r) => {
      const li = document.createElement('li');
      const why = r.trigger === 'detector' ? `검출기 ${(r.alarms || []).map((a) => a.detectors.join('/')).join(', ')}` : r.trigger === 'candidate' ? `후보 ${r.model}` : `주기 ${r.every_days}일`;
      li.textContent = `${r.job}: ${why}, 스트림 ${r.cutoff_time ? r.cutoff_time.slice(0, 13) : ''} 시점, 기존 ${r.active_version}`;
      rl.appendChild(li);
    });
  }
  async function runForecast() {
    const w = await getJSON('/v1/replay/window');
    const t0 = performance.now();
    const fc = await postJSON('/v1/forecast', { history: w.history, origin: w.origin, record: false });
    const ms = performance.now() - t0;
    const ci = parseInt($('fc-channel').value, 10) || 0;
    drawForecast(w, fc, ci);
    $('fc-status').textContent = `${fc.model_version} · 기준 시각 ${w.origin.slice(0, 16)} · 왕복 ${ms.toFixed(0)} ms (모델 ${fc.latency_ms.toFixed(2)} ms)${w.replay_active ? '' : ' · 리플레이를 켜면 예측 뒤의 실제값도 그립니다'}`;
    const p = state.profile;
    $('curl-example').textContent = `curl -s -X POST ${location.origin}/v1/forecast \\\n  -H 'content-type: application/json' \\\n  -d '{"history": [[${(p ? p.channels : w.channels).map(() => '…').join(', ')}] × ${w.history.length}], "origin": "${w.origin.slice(0, 19)}"}'\n# → {"model_version": "${fc.model_version}", "forecast": [[…] × ${fc.forecast.length}], "timestamps": [...], "latency_ms": ${fc.latency_ms.toFixed(2)}}`;
  }
  function drawForecast(w, fc, ci) {
    const svg = $('chart-forecast');
    clear(svg);
    const W = 640, H = 240, pad = { l: 44, r: 12, t: 12, b: 28 };
    const tail = Math.min(96, w.history.length);
    const hist = w.history.slice(-tail).map((r) => r[ci]);
    const pred = fc.forecast.map((r) => r[ci]);
    const actual = (w.actual_next || []).map((r) => r[ci]);
    const all = hist.concat(pred, actual);
    const ymin = Math.min(...all), ymax = Math.max(...all), span = ymax - ymin || 1;
    const n = tail + pred.length;
    const x = scale([0, n - 1], [pad.l, W - pad.r]);
    const y = scale([ymin - span * 0.08, ymax + span * 0.08], [H - pad.b, pad.t]);
    axes(svg, W, H, pad, x, y, [0, n - 1], [ymin - span * 0.08, ymax + span * 0.08], (i) => `${Math.round(i) - tail + 1}h`, (v) => v.toFixed(1));
    const sx = x(tail - 1);
    svg.appendChild(el('line', { x1: sx, x2: sx, y1: pad.t, y2: H - pad.b, stroke: 'var(--muted)', 'stroke-dasharray': '6 4' }));
    svg.appendChild(el('text', { x: sx - 4, y: pad.t + 10, class: 'tick', 'text-anchor': 'end' }, '지금'));
    polyline(svg, hist.map((v, i) => [x(i), y(v)]), { stroke: 'var(--ink)', 'stroke-width': 1.5 });
    polyline(svg, [[x(tail - 1), y(hist[tail - 1])]].concat(pred.map((v, i) => [x(tail + i), y(v)])), { stroke: versionColor(fc.model_version), 'stroke-width': 3 });
    if (actual.length) polyline(svg, [[x(tail - 1), y(hist[tail - 1])]].concat(actual.map((v, i) => [x(tail + i), y(v)])), { stroke: 'var(--ink)', 'stroke-width': 1.5, 'stroke-dasharray': '4 3', opacity: 0.8 });
    const cname = (state.profile ? state.profile.channels : w.channels)[ci];
    svg.appendChild(el('text', { x: W - pad.r, y: pad.t + 10, class: 'tick', 'text-anchor': 'end' }, `${cname} · ${fc.model_version}`));
    if (actual.length) {
      const mae = actual.reduce((s, a, i) => s + Math.abs(a - pred[i]), 0) / actual.length;
      svg.appendChild(el('text', { x: W - pad.r, y: pad.t + 24, class: 'tick', 'text-anchor': 'end' }, `다음 ${actual.length}h MAE ${mae.toFixed(3)}`));
    }
  }
  $('btn-forecast').addEventListener('click', () => runForecast().catch((err) => { $('fc-status').textContent = `오류: ${err.message}`; }));
  $('fc-channel').addEventListener('change', () => runForecast().catch(() => {}));

  // ---- 4 · monitor --------------------------------------------------------------------------
  function drawDaily(daily, alarms, baseline) {
    const svg = $('chart-daily');
    clear(svg);
    const W = 640, H = 240, pad = { l: 44, r: 12, t: 12, b: 28 };
    if (!daily || daily.length < 2) {
      svg.appendChild(el('text', { x: W / 2, y: H / 2, class: 'tick', 'text-anchor': 'middle' }, '아직 하루치 오차가 모이지 않았습니다. 리플레이를 진행해 보세요.'));
      return;
    }
    const ys = daily.map((d) => d.mae);
    const ymax = Math.max(...ys, baseline || 0) * 1.1, ymin = 0;
    const x = scale([0, daily.length - 1], [pad.l, W - pad.r]);
    const y = scale([ymin, ymax], [H - pad.b, pad.t]);
    axes(svg, W, H, pad, x, y, [0, daily.length - 1], [ymin, ymax], (i) => daily[Math.round(i)].day.slice(5), (v) => v.toFixed(2));
    if (baseline) {
      svg.appendChild(el('line', { x1: pad.l, x2: W - pad.r, y1: y(baseline), y2: y(baseline), stroke: 'var(--muted)', 'stroke-dasharray': '6 4' }));
      svg.appendChild(el('text', { x: W - pad.r, y: y(baseline) - 4, class: 'tick', 'text-anchor': 'end' }, `검증 MAE ${baseline.toFixed(3)}`));
    }
    let seg = [], segV = null;
    const flush = () => { if (seg.length) polyline(svg, seg.map(([i, v]) => [x(i), y(v)]), { stroke: versionColor(segV) }); };
    daily.forEach((d, i) => {
      const v = (d.versions && d.versions[d.versions.length - 1]) || 'v0001';
      if (v !== segV) { flush(); seg = seg.length ? [seg[seg.length - 1]] : []; segV = v; }
      seg.push([i, d.mae]);
    });
    flush();
    const alarmDays = new Set((alarms || []).map((a) => a.day));
    daily.forEach((d, i) => {
      if (alarmDays.has(d.day)) svg.appendChild(el('path', { d: `M${x(i)},${y(d.mae) - 10} l5,8 h-10 z`, fill: 'var(--warn)' }));
    });
  }
  function renderMonitor(mon) {
    $('stat-rolling').textContent = fmt(mon.rolling_7d_mae, 3);
    $('stat-baseline').textContent = fmt(mon.baseline_val_mae, 3);
    $('stat-resolved').textContent = mon.resolved_forecasts;
    $('stat-jobs').textContent = mon.pending_jobs.length;
    const alert = mon.rolling_7d_mae && mon.baseline_val_mae && mon.rolling_7d_mae > mon.baseline_val_mae * 1.2;
    $('stat-rolling').parentElement.classList.toggle('alert', !!alert);
    const tb = $('detectors').querySelector('tbody');
    tb.innerHTML = '';
    mon.detectors.forEach((d) => {
      const tr = document.createElement('tr');
      const statVal = d.statistic !== undefined ? d.statistic : (d.rolling !== undefined ? d.rolling : d.mean);
      const thr = d.threshold !== undefined ? d.threshold : (d.delta !== undefined ? `δ=${d.delta}` : '—');
      const alarmed = typeof statVal === 'number' && typeof thr === 'number' ? statVal > thr
        : mon.alarms.some((a) => a.detectors.includes(d.name) && a.day === mon.last_alarm_day && mon.days_closed - mon.skipped_days < 7);
      tr.innerHTML = `<td>${d.name}</td><td class="num">${typeof statVal === 'number' ? fmt(statVal, 3) : '—'}</td><td class="num">${typeof thr === 'number' ? fmt(thr, 3) : thr}</td><td class="${alarmed ? 'state-alarm' : 'state-ok'}">${alarmed ? '임계 초과' : '정상'}</td>`;
      tb.appendChild(tr);
    });
    drawDaily(mon.daily, mon.alarms, mon.baseline_val_mae);
  }
  function renderReplay(pos) {
    state.replay = pos;
    const on = pos && pos.active;
    ['btn-step1', 'btn-step7', 'btn-step30', 'btn-auto'].forEach((id) => { $(id).disabled = !on; });
    $('chip-stream').textContent = on ? `스트림 ${pos.current_time ? pos.current_time.slice(0, 13) : ''}` : '리플레이 꺼짐';
    $('chip-stream').classList.toggle('muted', !on);
    if (on) {
      $('progress-bar').style.width = `${(pos.progress * 100).toFixed(1)}%`;
      $('replay-pos').textContent = `${pos.cursor.toLocaleString()} / ${pos.n_rows.toLocaleString()} 행 · 현재 ${pos.current_time ? pos.current_time.slice(0, 16) : ''} · 주기 재학습 ${pos.retrain_schedule_days || '없음'}`;
    }
  }
  async function startReplay(days) {
    await withKey(() => postJSON('/v1/replay/start', days > 0 ? { schedule_days: days } : {}));
    await refresh();
  }
  async function step(steps) {
    try { await postJSON('/v1/replay/step', { steps }); await refresh(); } catch (err) { $('replay-pos').textContent = `오류: ${err.message}`; }
  }
  $('btn-start').addEventListener('click', () => startReplay(parseInt($('schedule-days').value, 10) || 0).catch((err) => { $('replay-pos').textContent = `오류: ${err.message}`; }));
  $('btn-step1').addEventListener('click', () => step(24));
  $('btn-step7').addEventListener('click', () => step(24 * 7));
  $('btn-step30').addEventListener('click', () => step(24 * 30));
  $('btn-auto').addEventListener('click', () => {
    if (state.auto) { clearInterval(state.auto); state.auto = null; $('btn-auto').textContent = '자동 재생'; return; }
    $('btn-auto').textContent = '자동 재생 중지';
    state.auto = setInterval(() => step(24), 700);
  });

  // ---- 5 · policy ---------------------------------------------------------------------------
  function drawPareto(container, dataset, rows) {
    const fig = document.createElement('figure');
    const svg = el('svg', { viewBox: '0 0 320 220', role: 'img', 'aria-label': `${dataset} 재학습 횟수 대 MAE` });
    const W = 320, H = 220, pad = { l: 46, r: 10, t: 12, b: 28 };
    const xs = rows.map((r) => r.n_refits), ys = rows.map((r) => r.mae);
    const xmax = Math.max(...xs, 1), ymin = Math.min(...ys), ymax = Math.max(...ys);
    const span = Math.max(ymax - ymin, 1e-6);
    const x = scale([0, xmax], [pad.l, W - pad.r]);
    const y = scale([ymin - span * 0.1, ymax + span * 0.1], [H - pad.b, pad.t]);
    axes(svg, W, H, pad, x, y, [0, xmax], [ymin - span * 0.1, ymax + span * 0.1], (v) => Math.round(v), (v) => v.toFixed(3));
    const kinds = { never: 'var(--muted)', periodic: 'var(--v0)', ratio: 'var(--v1)', ph: 'var(--v2)', adwin: 'var(--v3)', warm: 'var(--v5)' };
    rows.forEach((r) => {
      const gated = r.policy.endsWith('+gate');
      const kind = r.policy.split('+')[0].split('-')[0];
      const color = kinds[kind] || 'var(--ink)';
      const shape = kind === 'periodic' || kind === 'never' ? 'circle' : 'rect';
      const node = shape === 'circle'
        ? el('circle', { cx: x(r.n_refits), cy: y(r.mae), r: 4, fill: gated ? 'var(--card)' : color, stroke: color, 'stroke-width': 1.5 })
        : el('rect', { x: x(r.n_refits) - 3.5, y: y(r.mae) - 3.5, width: 7, height: 7, fill: gated ? 'var(--card)' : color, stroke: color, 'stroke-width': 1.5 });
      node.appendChild(el('title', {}, `${r.policy}: MAE ${r.mae.toFixed(4)}, 재학습 ${r.n_refits}회`));
      svg.appendChild(node);
    });
    fig.appendChild(svg);
    const cap = document.createElement('figcaption');
    cap.textContent = `${dataset} — 가로: 실제 교체 횟수, 세로: 스트림 MAE (시드 평균). ● 주기, ■ 감시 기반, 속이 빈 표시 = 승격 게이트 적용.`;
    fig.appendChild(cap);
    container.appendChild(fig);
  }
  function renderEvidence(ev) {
    state.evidence = ev;
    const grid = $('pareto-grid');
    grid.innerHTML = '';
    const tb = $('results-table').querySelector('tbody');
    tb.innerHTML = '';
    if (!ev || !ev.datasets) {
      $('evidence-note').textContent = '오프라인 실험 결과 파일(static/evidence.json)이 아직 없습니다. `metronome report` 가 생성합니다.';
      return;
    }
    $('evidence-note').textContent = ev.note || '';
    Object.entries(ev.datasets).forEach(([ds, d]) => {
      drawPareto(grid, ds, d.policies);
      const by = Object.fromEntries(d.policies.map((p) => [p.policy, p]));
      const rep = d.representative || {};
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${ds}</td><td class="num">${fmt(by.never && by.never.mae)}</td><td class="num">${fmt(by['periodic-7'] && by['periodic-7'].mae)}</td><td class="num">${fmt(by['periodic-1'] && by['periodic-1'].mae)}</td><td>${rep.policy || '—'} (${fmt(rep.mae)})</td><td class="num">${rep.n_refits !== undefined ? rep.n_refits.toFixed(0) : '—'}</td>`;
      tb.appendChild(tr);
    });
    renderRecommendation();
  }
  function renderRecommendation() {
    const ev = state.evidence, ds = state.dataset;
    const box = $('policy-recommend');
    if (!ev || !ev.datasets || !ds || !ev.datasets[ds]) { box.textContent = '이 데이터셋의 오프라인 결과가 없습니다. 검출기 기반 재생은 그대로 됩니다.'; return; }
    const d = ev.datasets[ds];
    const by = Object.fromEntries(d.policies.map((p) => [p.policy, p]));
    const never = by.never, daily = by['periodic-1'], weeklyGate = by['periodic-7+gate'] || by['periodic-7'], rep = d.representative;
    const gain = never && daily ? ((never.mae - daily.mae) / never.mae * 100) : null;
    const parts = [];
    parts.push(`<p><b>${esc(ds)}</b> 의 오프라인 실험(시드 평균): 재학습 없이 MAE ${fmt(never && never.mae)}, 매일 재학습 ${fmt(daily && daily.mae)} (${gain === null ? '—' : Math.abs(gain).toFixed(1) + '% ' + (gain >= 0 ? '낮음' : '높음')}, ${daily ? Math.round(daily.n_refits) : '—'}회 교체).</p>`);
    if (rep) parts.push(`<p>대표 감시 정책 <b>${esc(rep.policy)}</b>: MAE ${fmt(rep.mae)} 를 ${Math.round(rep.n_refits)}회 교체로 얻습니다. 매일 재학습 이득의 대부분을 수십 배 적은 교체로 가져가는 쪽입니다.</p>`);
    if (weeklyGate) parts.push(`<p>주 1회 재학습${weeklyGate.policy.endsWith('+gate') ? ' + 승격 게이트' : ''}: MAE ${fmt(weeklyGate.mae)}, ${Math.round(weeklyGate.n_refits)}회 교체. 이 정책이 Airflow DAG 로 올라가 있습니다.</p>`);
    parts.push('<p class="muted">아래 버튼은 그 정책으로 스트림 재생을 시작하고 감시 탭으로 이동합니다. 재생 중 재학습이 일어나면 모델 비교 탭의 작업 목록에도 나타납니다.</p>');
    box.className = '';
    box.innerHTML = parts.join('');
  }
  async function replayWithPolicy(days) {
    showPanel('monitor');
    $('schedule-days').value = String(days);
    try { await startReplay(days); } catch (err) { $('replay-pos').textContent = `오류: ${err.message}`; }
  }
  $('btn-policy-detector').addEventListener('click', () => replayWithPolicy(0));
  $('btn-policy-weekly').addEventListener('click', () => replayWithPolicy(7));
  $('btn-policy-never').addEventListener('click', async () => {
    showPanel('monitor');
    $('schedule-days').value = '0';
    try { await withKey(() => postJSON('/v1/replay/start', { wait_for_retrain: false })); await refresh(); } catch (err) { $('replay-pos').textContent = `오류: ${err.message}`; }
  });

  // ---- polling ------------------------------------------------------------------------------
  let profileLoaded = false;
  async function refresh() {
    try {
      const [health, ready, models, mon, events, replay, candidates] = await Promise.all([
        getJSON('/health'), fetch('/ready', { cache: 'no-store' }).then((r) => r.ok), getJSON('/v1/models'), getJSON('/v1/monitor'), getJSON('/v1/events'), getJSON('/v1/replay'), getJSON('/v1/candidates'),
      ]);
      $('chip-ready').textContent = ready ? '서비스 준비됨' : '모델 준비 안 됨';
      $('chip-ready').className = `chip ${ready ? 'ok' : 'bad'}`;
      $('foot-version').textContent = `metronome ${health.version}`;
      renderModel(models); renderMonitor(mon); renderEvents(events); renderReplay(replay); renderCandidates(candidates);
      if (!profileLoaded) {
        profileLoaded = true;
        getJSON('/v1/data/profile').then((p) => { renderProfile(p); renderRecommendation(); }).catch((err) => { $('dataset-kv').innerHTML = `<dt>오류</dt><dd>${esc(err.message)}</dd>`; });
        getJSON('/v1/leaderboard').then(renderLeaderboard).catch(() => {});
      }
    } catch (err) {
      $('chip-ready').textContent = `연결 실패: ${err.message}`;
      $('chip-ready').className = 'chip bad';
    }
  }

  const initial = (location.hash || '#data').slice(1);
  if (document.getElementById(`panel-${initial}`)) showPanel(initial);
  getJSON('/static/evidence.json').then(renderEvidence).catch(() => renderEvidence(null));
  refresh();
  setInterval(refresh, 3000);
})();
