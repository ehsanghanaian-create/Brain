/* SEO Brain — first-party tracker. Served per site at /api/v1/track/{site_id}/t.js with the key injected.
 * No cookies, no localStorage, no fingerprinting: the visitor id is a daily server-side hash that rotates
 * at midnight. Beacons go out as text/plain so they are CORS-simple — no preflight, no CORS config to keep.
 * Set window.__seoBrainDNT = true before this script to honour Do-Not-Track.
 */
(function () {
  'use strict';
  var KEY = '__WRITE_KEY__';
  var URL_ = '__ENDPOINT__';
  if (!KEY || KEY.charAt(0) === '_') return;
  if (window.__seoBrainDNT && (navigator.doNotTrack === '1' || window.doNotTrack === '1')) return;
  if (window.__seoBrainLoaded) return;
  window.__seoBrainLoaded = true;

  var queue = [];
  var sentScroll = {};
  var started = Date.now();
  var lastPath = location.pathname;
  var timer = null;

  function path() {
    return location.pathname || '/';
  }

  function push(type, extra) {
    var e = { t: type, p: path() };
    if (extra) for (var k in extra) if (extra.hasOwnProperty(k)) e[k] = extra[k];
    queue.push(e);
    if (queue.length >= 20) flush();
    else schedule();
  }

  function schedule() {
    if (timer) return;
    timer = setTimeout(function () {
      timer = null;
      flush();
    }, 4000);
  }

  function flush() {
    if (!queue.length) return;
    var body = JSON.stringify({
      k: KEY,
      v: 1,
      r: document.referrer || '',
      u: location.href,
      d: device(),
      e: queue.splice(0, queue.length)
    });
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(URL_, new Blob([body], { type: 'text/plain;charset=UTF-8' }));
        return;
      }
    } catch (err) { /* fall through to fetch */ }
    try {
      fetch(URL_, { method: 'POST', body: body, keepalive: true, mode: 'no-cors', headers: { 'Content-Type': 'text/plain' } });
    } catch (err2) { /* a dropped beacon is never worth an error in the page */ }
  }

  function device() {
    var w = window.innerWidth || 1024;
    return w < 768 ? 'mobile' : w < 1024 ? 'tablet' : 'desktop';
  }

  /* a short, stable-ish description of what was clicked: id, else tag.class, else text */
  function describe(el) {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    var cls = (el.className && typeof el.className === 'string') ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    var base = el.tagName.toLowerCase() + (cls ? '.' + cls : '');
    var txt = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60);
    return txt ? base + '|' + txt : base;
  }

  function docHeight() {
    var b = document.body, e = document.documentElement;
    return Math.max(b ? b.scrollHeight : 0, e ? e.scrollHeight : 0, window.innerHeight || 0) || 1;
  }

  /* ---- pageview ---- */
  push('pageview');

  /* ---- scroll depth: one event per quarter, once per page ---- */
  function onScroll() {
    var top = window.pageYOffset || document.documentElement.scrollTop || 0;
    var reached = Math.round(((top + (window.innerHeight || 0)) / docHeight()) * 100);
    var marks = [25, 50, 75, 100];
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      if (reached >= m && !sentScroll[m]) {
        sentScroll[m] = 1;
        push('scroll', { v: m });
      }
    }
  }

  /* ---- clicks: phone links are the conversion; everything else is heat-map material ---- */
  function onClick(ev) {
    var el = ev.target;
    var depth = 0;
    while (el && el !== document.body && depth < 6) {
      var tag = el.tagName ? el.tagName.toLowerCase() : '';
      var href = el.getAttribute ? (el.getAttribute('href') || '') : '';
      if (tag === 'a' && href.indexOf('tel:') === 0) {
        push('tel_click', { l: href.replace('tel:', '').slice(0, 40), x: nx(ev), y: ny(ev) });
        flush();
        return;
      }
      if (tag === 'a' && href.indexOf('https://wa.me') === 0) {
        push('click', { l: 'whatsapp', x: nx(ev), y: ny(ev) });
        flush();
        return;
      }
      el = el.parentNode;
      depth++;
    }
    push('click', { l: describe(ev.target), x: nx(ev), y: ny(ev) });
  }

  function nx(ev) {
    return Math.round(((ev.clientX || 0) / (window.innerWidth || 1)) * 1000) / 1000;
  }

  function ny(ev) {
    var top = window.pageYOffset || document.documentElement.scrollTop || 0;
    return Math.round((((ev.clientY || 0) + top) / docHeight()) * 1000) / 1000;
  }

  /* ---- forms ---- */
  function onSubmit(ev) {
    var f = ev.target;
    push('form_submit', { l: (f && (f.id || f.name || f.getAttribute('action'))) || 'form' });
    flush();
  }

  /* ---- engagement heartbeat, then a final exit beacon ---- */
  var beats = 0;
  var beat = setInterval(function () {
    if (document.hidden) return;
    beats++;
    if (beats % 3 === 0) push('engaged', { v: beats * 10 });
  }, 10000);

  function finish() {
    push('exit', { v: Math.round((Date.now() - started) / 1000) });
    flush();
  }

  /* ---- SPA / history navigations (rare on these sites, cheap to support) ---- */
  function maybeNavigated() {
    if (location.pathname === lastPath) return;
    lastPath = location.pathname;
    sentScroll = {};
    started = Date.now();
    push('pageview');
  }

  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('click', onClick, true);
  addEventListener('submit', onSubmit, true);
  addEventListener('popstate', maybeNavigated);
  addEventListener('visibilitychange', function () {
    if (document.hidden) flush();
  });
  addEventListener('pagehide', finish);
  if (!('onpagehide' in window)) addEventListener('beforeunload', finish);
  addEventListener('unload', function () {
    clearInterval(beat);
  });
  onScroll();
})();
