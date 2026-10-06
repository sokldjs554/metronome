/* Metronome dashboard: plain JS + inline SVG, no external dependencies. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const fmt = (x, d = 4) => (x === null || x === undefined || Number.isNaN(x)) ? '—' : Number(x).toFixed(d);
  const versionColor = (v) => {
    const n = parseInt(String(v).replace(/\D/g, ''), 10) || 0;
    return `var(--v${(n - 1 + 6) % 6})`;
  };
  const state = { auto: null, apiKey: null, evidence: null, replay: null };

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
    if (!r.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : `${url}: ${r.status}`);
    return data;
  }

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

  // ---- daily MAE chart ----------------------------------------------------------------------
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
    // one polyline per contiguous version segment
    let seg = [], segV = null;
    const flush = () => {
      if (seg.length) {
        const pts = seg.map(([i, v]) => `${x(i)},${y(v)}`).join(' ');
        svg.appendChild(el('polyline', { points: pts, class: 'series', stroke: versionColor(segV) }));
      }
    };
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

  // ---- Pareto chart (offline evidence) -----------------------------------------------------
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

  // ---- renderers ----------------------------------------------------------------------------
  function renderModel(models) {
    const kv = $('model-kv');
    kv.innerHTML = '';
    const a = models.active;
    const rows = a ? [
      ['버전', a.version], ['등록', a.created_at || '—'],
      ['검증 MAE (고정 척도)', fmt(a.metrics && a.metrics.val_mae_fixed)],
      ['ONNX parity 편차', a.parity_max_abs_diff === undefined ? '—' : Number(a.parity_max_abs_diff).toExponential(2)],
      ['학습 데이터', a.provenance && a.provenance.cutoff_time ? `… ${a.provenance.cutoff_time.slice(0, 16)} (${a.provenance.trigger || ''})` : '—'],
      ['ONNX SHA-256', a.onnx_sha256 ? a.onnx_sha256.slice(0, 16) + '…' : '—'],
      ['등록된 버전 수', String(models.versions.length)],
    ] : [['상태', models.load_error || '활성 모델 없음']];
    rows.forEach(([k, v]) => { const dt = document.createElement('dt'); dt.textContent = k; const dd = document.createElement('dd'); dd.textContent = v; kv.append(dt, dd); });
    $('chip-version').textContent = a ? `모델 ${a.version}` : '모델 없음';
    $('chip-version').style.color = a ? versionColor(a.version) : '';
  }
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
      const why = r.trigger === 'detector' ? `검출기 ${(r.alarms || []).map((a) => a.detectors.join('/')).join(', ')}` : `주기 ${r.every_days}일`;
      li.textContent = `${r.job}: ${why}, 스트림 ${r.cutoff_time ? r.cutoff_time.slice(0, 13) : ''} 시점, 기존 ${r.active_version}`;
      rl.appendChild(li);
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
      const alarmed = mon.alarms.some((a) => a.detectors.includes(d.name) && a.day === mon.last_alarm_day);
      tr.innerHTML = `<td>${d.name}</td><td class="num">${typeof statVal === 'number' ? fmt(statVal, 3) : '—'}</td><td class="num">${typeof thr === 'number' ? fmt(thr, 3) : thr}</td><td class="${alarmed ? 'state-alarm' : 'state-ok'}">${alarmed ? '경보' : '정상'}</td>`;
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
  function renderEvidence(ev) {
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
  }

  // ---- polling ------------------------------------------------------------------------------
  async function refresh() {
    try {
      const [health, ready, models, mon, events, replay] = await Promise.all([
        getJSON('/health'), fetch('/ready', { cache: 'no-store' }).then((r) => r.ok), getJSON('/v1/models'), getJSON('/v1/monitor'), getJSON('/v1/events'), getJSON('/v1/replay'),
      ]);
      $('chip-ready').textContent = ready ? '서비스 준비됨' : '모델 준비 안 됨';
      $('chip-ready').className = `chip ${ready ? 'ok' : 'bad'}`;
      $('foot-version').textContent = `metronome ${health.version}`;
      renderModel(models); renderMonitor(mon); renderEvents(events); renderReplay(replay);
    } catch (err) {
      $('chip-ready').textContent = `연결 실패: ${err.message}`;
      $('chip-ready').className = 'chip bad';
    }
  }

  async function step(steps) {
    try {
      await postJSON('/v1/replay/step', { steps });
      await refresh();
    } catch (err) { $('replay-pos').textContent = `오류: ${err.message}`; }
  }

  $('btn-start').addEventListener('click', async () => {
    const days = parseInt($('schedule-days').value, 10) || 0;
    try {
      await postJSON('/v1/replay/start', days > 0 ? { schedule_days: days } : {});
      await refresh();
    } catch (err) {
      if (/401/.test(err.message) || /API key/.test(err.message)) {
        state.apiKey = window.prompt('API key (METRONOME_API_KEY)') || null;
        if (state.apiKey) $('btn-start').click();
      } else { $('replay-pos').textContent = `오류: ${err.message}`; }
    }
  });
  $('btn-step1').addEventListener('click', () => step(24));
  $('btn-step7').addEventListener('click', () => step(24 * 7));
  $('btn-step30').addEventListener('click', () => step(24 * 30));
  $('btn-auto').addEventListener('click', () => {
    if (state.auto) { clearInterval(state.auto); state.auto = null; $('btn-auto').textContent = '자동 재생'; return; }
    $('btn-auto').textContent = '자동 재생 중지';
    state.auto = setInterval(() => step(24), 700);
  });

  getJSON('/static/evidence.json').then(renderEvidence).catch(() => renderEvidence(null));
  refresh();
  setInterval(refresh, 3000);
})();
