// MFD performance probe. Load as the FIRST script in <head> so the long-task
// observer sees the whole page load (Chrome 69 has no buffered observers).
// ES5 only, and cheap by design: no requestAnimationFrame loop, one 250 ms
// timer. Reports go by <img> beacon to beacon_logger.py on port 8099 of the
// host that served the page.
//
// Reports:
//   t=boot   immediately when the script starts (proves a fresh load).
//   t=load   once, 5 s after window load: navigation + paint timings,
//            resources, long tasks during load, JS heap.
//   t=idle   every 60 s for as long as the page lives (also shows whether
//            pages keep running after the MFD leaves them): long tasks +
//            timer lag in that minute; vis = document.visibilityState now.
//            hid = ms of the window the tab was hidden; browsers throttle
//            hidden tabs' timers, so windows with hid > 0 aren't comparable.
//   t=err    uncaught errors.
//   t=input  touch/mouse/click/key events that reached the page.
// Traffic fields: wsg/wsk = WebSocket messages from gateway/other hosts,
// wskb = their KB, fx = fetch() calls (per report window).
(function () {
  if (!window.performance || !performance.timing) return;

  var BEACON = location.protocol + '//' + location.hostname + ':8099/b';
  var run = Math.random().toString(36).slice(2, 8);
  var IDLE_WINDOW_MS = 60000;
  var LAG_INTERVAL_MS = 250;

  function send(type, data) {
    var q = ['t=' + type, 'r=' + run, 'p=' + encodeURIComponent(location.pathname), 'q=' + encodeURIComponent(location.search), 'h=' + encodeURIComponent(location.hash)];
    for (var k in data) {
      if (data.hasOwnProperty(k)) q.push(k + '=' + encodeURIComponent(data[k]));
    }
    new Image().src = BEACON + '?' + q.join('&');
  }

  window.addEventListener('error', function (e) {
    send('err', { m: String(e.message).slice(0, 200), s: String(e.filename || '').slice(-80), l: e.lineno, c: e.colno });
  });

  // Long tasks: [startTime, duration] in ms since navigation start.
  var longTasks = [];
  try {
    new PerformanceObserver(function (list) {
      var entries = list.getEntries();
      for (var i = 0; i < entries.length; i++) {
        longTasks.push([entries[i].startTime, entries[i].duration]);
      }
    }).observe({ entryTypes: ['longtask'] });
  } catch (e) { /* not supported: lt* fields report 0 */ }

  function longTaskStats(from, to) {
    var n = 0, sum = 0, max = 0;
    for (var i = 0; i < longTasks.length; i++) {
      var t = longTasks[i];
      if (t[0] >= from && t[0] < to) {
        n++;
        sum += t[1];
        if (t[1] > max) max = t[1];
      }
    }
    return { ltn: n, lts: Math.round(sum), ltm: Math.round(max) };
  }

  // Live-update traffic: WebSocket messages from the page's own host
  // (gateway) vs elsewhere (e.g. Signal K :3000), plus fetch() calls.
  var wsGateway = 0, wsOther = 0, wsBytes = 0, fetches = 0;
  var NativeWS = window.WebSocket;
  if (NativeWS) {
    var CountingWS = function (url, protocols) {
      var ws = protocols === undefined ? new NativeWS(url) : new NativeWS(url, protocols);
      var fromGateway = String(url).indexOf('//' + location.host + '/') !== -1;
      ws.addEventListener('message', function (e) {
        if (fromGateway) wsGateway++; else wsOther++;
        wsBytes += (e.data && e.data.length) || 0;
      });
      return ws;
    };
    CountingWS.prototype = NativeWS.prototype;
    CountingWS.CONNECTING = 0; CountingWS.OPEN = 1; CountingWS.CLOSING = 2; CountingWS.CLOSED = 3;
    window.WebSocket = CountingWS;
  }
  if (window.fetch) {
    var nativeFetch = window.fetch;
    window.fetch = function () { fetches++; return nativeFetch.apply(this, arguments); };
  }
  function takeTraffic() {
    var r = { wsg: wsGateway, wsk: wsOther, wskb: Math.round(wsBytes / 1024), fx: fetches };
    wsGateway = 0; wsOther = 0; wsBytes = 0; fetches = 0;
    return r;
  }

  // Render timing: wraps the app's top-level render functions (if present)
  // after the page's own scripts have run. Reported as rf=name:calls:ms,...
  var RENDER_FNS = ['flushRenders', 'renderControl', 'renderSensors', 'renderPower', 'renderOverviewEnv', 'renderEssentials', 'renderOverviewLights'];
  var renderStats = {};
  document.addEventListener('DOMContentLoaded', function () {
    RENDER_FNS.forEach(function (name) {
      var fn = window[name];
      if (typeof fn !== 'function') return;
      window[name] = function () {
        var t0 = performance.now();
        try { return fn.apply(this, arguments); }
        finally {
          var st = renderStats[name] || (renderStats[name] = { n: 0, ms: 0 });
          st.n++; st.ms += performance.now() - t0;
        }
      };
    });
  });
  function takeRenderStats() {
    var parts = [];
    for (var k in renderStats) {
      if (renderStats.hasOwnProperty(k)) parts.push(k + ':' + renderStats[k].n + ':' + Math.round(renderStats[k].ms));
    }
    renderStats = {};
    return { rf: parts.join(',') };
  }

  // Timer lag: how late a 250 ms interval fires -- main-thread contention
  // that long tasks alone miss (many short tasks, rendering work).
  var lagSum = 0, lagMax = 0, lagN = 0, lastTick = performance.now();
  setInterval(function () {
    var now = performance.now();
    var lag = Math.max(0, now - lastTick - LAG_INTERVAL_MS);
    lagSum += lag;
    lagN++;
    if (lag > lagMax) lagMax = lag;
    lastTick = now;
  }, LAG_INTERVAL_MS);

  function takeLag() {
    var r = { lagavg: lagN ? Math.round(lagSum / lagN) : 0, lagmax: Math.round(lagMax) };
    lagSum = 0; lagMax = 0; lagN = 0;
    return r;
  }

  // Hidden time, so throttled background windows can be discarded.
  var hiddenMs = 0, hiddenSince = document.hidden ? performance.now() : null;
  document.addEventListener('visibilitychange', function () {
    var now = performance.now();
    if (document.hidden) hiddenSince = now;
    else if (hiddenSince !== null) { hiddenMs += now - hiddenSince; hiddenSince = null; }
  });
  function takeHidden() {
    var now = performance.now();
    var ms = hiddenMs + (hiddenSince !== null ? now - hiddenSince : 0);
    hiddenMs = 0;
    if (hiddenSince !== null) hiddenSince = now;
    return Math.round(ms);
  }

  function heapMB() {
    return performance.memory ? (performance.memory.usedJSHeapSize / 1048576).toFixed(1) : '';
  }

  function merge(a, b) {
    for (var k in b) if (b.hasOwnProperty(k)) a[k] = b[k];
    return a;
  }

  function loadReport() {
    var t = performance.timing, n0 = t.navigationStart, now = performance.now();
    var d = {
      resp: t.responseEnd - n0,
      dom: t.domInteractive - n0,
      dcl: t.domContentLoadedEventEnd - n0,
      load: t.loadEventEnd - n0,
      heap: heapMB()
    };
    var paints = performance.getEntriesByType ? performance.getEntriesByType('paint') : [];
    for (var i = 0; i < paints.length; i++) {
      if (paints[i].name === 'first-paint') d.fp = Math.round(paints[i].startTime);
      if (paints[i].name === 'first-contentful-paint') d.fcp = Math.round(paints[i].startTime);
    }
    var res = performance.getEntriesByType ? performance.getEntriesByType('resource') : [];
    var bytes = 0;
    for (var j = 0; j < res.length; j++) bytes += res[j].transferSize || 0;
    var nav = performance.getEntriesByType ? performance.getEntriesByType('navigation')[0] : null;
    d.res = res.length;
    d.kb = Math.round((bytes + ((nav && nav.transferSize) || 0)) / 1024);
    d.dom_nodes = document.getElementsByTagName('*').length;
    merge(d, longTaskStats(0, now));
    merge(d, takeLag());
    d.hid = takeHidden();
    merge(d, takeTraffic());
    merge(d, takeRenderStats());
    send('load', d);
  }

  function startIdleReports() {
    var reports = 0;
    var windowStart = performance.now();
    setInterval(function () {
      var now = performance.now();
      var d = merge(longTaskStats(windowStart, now), takeLag());
      d.busy = (100 * d.lts / (now - windowStart)).toFixed(1);
      d.heap = heapMB();
      d.hid = takeHidden();
      d.vis = document.visibilityState;
      merge(d, takeTraffic());
      merge(d, takeRenderStats());
      d.n = ++reports;
      send('idle', d);
      windowStart = now;
    }, IDLE_WINDOW_MS);
  }

  // Input reaching the page at all (vs. lost on the way from a remote):
  // one t=input report per event type, at most every 300 ms each.
  var lastInput = {};
  ['touchstart', 'mousedown', 'click', 'keydown'].forEach(function (type) {
    window.addEventListener(type, function (e) {
      var now = performance.now();
      if (lastInput[type] && now - lastInput[type] < 300) return;
      lastInput[type] = now;
      var el = e.target || {};
      send('input', { e: type, tag: el.tagName || '', id: el.id || '', cls: String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || '').slice(0, 40),
        k: e.key || '', x: e.touches && e.touches[0] ? Math.round(e.touches[0].clientX) : (e.clientX || ''), y: e.touches && e.touches[0] ? Math.round(e.touches[0].clientY) : (e.clientY || '') });
    }, true);
  });

  // Proof of a fresh load: report immediately, and show a badge with the
  // load time + run id (unchanged time = the MFD just resumed the old page),
  // with a button that forces a real reload.
  send('boot', {});
  document.addEventListener('DOMContentLoaded', function () {
    var d = new Date();
    function two(n) { return (n < 10 ? '0' : '') + n; }
    var badge = document.createElement('div');
    badge.style.cssText = 'position:fixed;left:4px;bottom:4px;z-index:99999;background:rgba(0,0,0,0.75);color:#fff;'
      + 'font:12px monospace;padding:4px 6px;border-radius:4px;display:flex;align-items:center;gap:8px;';
    badge.appendChild(document.createTextNode('loaded ' + two(d.getHours()) + ':' + two(d.getMinutes()) + ':' + two(d.getSeconds())
      + '  r=' + run + '  ' + (location.search || 'base')));
    var btn = document.createElement('button');
    btn.textContent = 'reload';
    btn.style.cssText = 'font:12px monospace;padding:2px 6px;';
    btn.onclick = function () { location.reload(); };
    badge.appendChild(btn);
    document.body.appendChild(badge);
  });

  window.addEventListener('load', function () {
    setTimeout(function () {
      loadReport();
      startIdleReports();
    }, 5000);
  });
})();
