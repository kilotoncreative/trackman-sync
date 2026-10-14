// Sync Trackman: runs inside your logged-in portal.trackmangolf.com page via
// the iOS Shortcuts action "Run JavaScript on Webpage". It reads your own
// activities with the portal's own login and returns them as JSON.
// GraphQL queries adapted from TrackPull (MIT, (c) 2026 criticalberne).
// Edit DAYS below: how far back to pull. Use 3650 once for a full backfill.
var DAYS = 30;

(async function () {
  var API = "https://api.trackmangolf.com/graphql";
  var SHOT_TYPES = ["SessionActivity", "VirtualRangeSessionActivity", "ShotAnalysisSessionActivity",
    "CombineTestActivity", "RangeFindMyDistanceActivity", "MapMyBagActivity", "MapMyBagSessionActivity",
    "BagMappingActivity", "VirtualGolfActivity", "VirtualGolfSessionActivity"];
  var MEASURE = "clubSpeed ballSpeed smashFactor attackAngle clubPath faceAngle faceToPath swingDirection " +
    "swingPlane dynamicLoft spinRate spinAxis spinLoft launchAngle launchDirection carry total carrySide " +
    "totalSide maxHeight landingAngle hangTime";
  var STROKE = "club time targetDistance measurement { " + MEASURE + " }";
  var PRO_BALL = "club time targetDistance measurement(measurementType: PRO_BALL_MEASUREMENT) { ballSpeed " +
    "ballSpin spinAxis carry carrySide total totalSide landingAngle launchAngle launchDirection maxHeight }";
  var LIST = "query GetPlayerActivities($skip: Int!, $take: Int!) { me { activities(skip: $skip, take: $take) " +
    "{ totalCount pageInfo { hasNextPage } items { id time kind __typename } } } }";

  function detailQueries(t) {
    var flat = function (s) { return "query FetchActivityById($id: ID!) { node(id: $id) { __typename ... on " + t + " { id time strokes { " + s + " } } } }"; };
    var grouped = function (s) { return "query FetchActivityById($id: ID!) { node(id: $id) { __typename ... on " + t + " { id time strokeGroups { club name strokes { " + s + " } } } } }"; };
    var qs = [flat(STROKE), grouped(STROKE)];
    if (/FindMyDistance|MapMyBag/.test(t)) qs.push(flat(PRO_BALL), grouped(PRO_BALL));
    return qs;
  }

  function hasShots(node) {
    if (!node) return false;
    var all = (node.strokes || []).slice();
    (node.strokeGroups || []).forEach(function (g) { all = all.concat(g.strokes || []); });
    return all.some(function (s) { return s && s.measurement; });
  }

  // 1. Find the auth the portal uses: watch its own GraphQL traffic.
  var headers = null, notes = [];
  function grab(url, h) {
    if (headers || !url || String(url).indexOf(API) !== 0 || !h) return;
    var out = {};
    if (typeof Headers !== "undefined" && h instanceof Headers) h.forEach(function (v, k) { out[k] = v; });
    else Object.keys(h).forEach(function (k) { out[k] = h[k]; });
    var keep = {};
    Object.keys(out).forEach(function (k) {
      var l = k.toLowerCase();
      if (l === "authorization" || l.indexOf("x-") === 0 || l.indexOf("tm-") === 0 || l.indexOf("apollographql-") === 0) keep[k] = out[k];
    });
    if (Object.keys(keep).some(function (k) { return k.toLowerCase() === "authorization"; })) headers = keep;
  }
  var origFetch = window.fetch;
  window.fetch = function (input, init) {
    try { grab(typeof input === "string" ? input : input && input.url, (init && init.headers) || (input && input.headers)); } catch (e) {}
    return origFetch.apply(this, arguments);
  };
  var xo = XMLHttpRequest.prototype.open, xs = XMLHttpRequest.prototype.setRequestHeader, xd = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this._tmUrl = u; this._tmH = {}; return xo.apply(this, arguments); };
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) { if (this._tmH) this._tmH[k] = v; return xs.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () { try { grab(this._tmUrl, this._tmH); } catch (e) {} return xd.apply(this, arguments); };

  // A token may also be embedded in the page or browser storage.
  function scanForJwt() {
    var srcs = [document.documentElement.innerHTML];
    try { if (window.__NEXT_DATA__) srcs.push(JSON.stringify(window.__NEXT_DATA__)); } catch (e) {}
    [localStorage, sessionStorage].forEach(function (s) {
      try { for (var i = 0; i < s.length; i++) srcs.push(s.getItem(s.key(i)) || ""); } catch (e) {}
    });
    for (var i = 0; i < srcs.length; i++) {
      var m = /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/.exec(srcs[i]);
      if (m) return { Authorization: "Bearer " + m[0] };
    }
    return null;
  }

  // Nudge the portal into making a GraphQL call so we can see its headers.
  function nudge() {
    try { document.dispatchEvent(new Event("visibilitychange")); window.dispatchEvent(new Event("focus")); window.dispatchEvent(new Event("online")); } catch (e) {}
    // In-app route change only (no page load, which would stop this script).
    try {
      var target = location.pathname.indexOf("/player/activities") === 0 ? "/player" : "/player/activities";
      history.pushState({}, "", target);
      window.dispatchEvent(new PopStateEvent("popstate", { state: {} }));
    } catch (e) {}
  }

  for (var i = 0; i < 30 && !headers; i++) {
    if (i === 0 || i === 6 || i === 14) nudge();
    await new Promise(function (r) { setTimeout(r, 500); });
  }
  if (headers) notes.push("auth: captured from portal traffic");
  if (!headers) { headers = scanForJwt(); if (headers) notes.push("auth: token found in page"); }
  if (!headers) { headers = {}; notes.push("auth: trying cookies only"); }

  async function gql(query, variables) {
    var h = Object.assign({ "Content-Type": "application/json", "Accept": "application/json" }, headers);
    var r = await origFetch.call(window, API, { method: "POST", credentials: "include", headers: h,
      body: JSON.stringify({ query: query, variables: variables }) });
    var text = await r.text();
    if (!r.ok) throw new Error("HTTP " + r.status + ": " + text.slice(0, 200));
    return JSON.parse(text);
  }

  try {
    // 2. List activities, newest first, until we pass the cutoff.
    var cutoff = Date.now() - DAYS * 86400000, acts = [], skip = 0;
    while (true) {
      var res = await gql(LIST, { skip: skip, take: 100 });
      if (!res.data || !res.data.me) throw new Error("Activity list failed: " + JSON.stringify(res.errors || res).slice(0, 300));
      var page = res.data.me.activities, items = page.items || [];
      acts = acts.concat(items);
      var oldest = items.length ? Date.parse(items[items.length - 1].time) : 0;
      if (!page.pageInfo || !page.pageInfo.hasNextPage || !items.length || oldest < cutoff) break;
      skip += 100;
    }
    acts = acts.filter(function (a) { return SHOT_TYPES.indexOf(a.__typename) >= 0 && Date.parse(a.time) >= cutoff; });

    // 3. Pull shot data for each.
    var out = [];
    for (var j = 0; j < acts.length; j++) {
      var qs = detailQueries(acts[j].__typename), node = null;
      for (var k = 0; k < qs.length && !hasShots(node); k++) {
        try { node = (await gql(qs[k], { id: acts[j].id })).data.node; } catch (e) { node = null; }
      }
      if (hasShots(node)) out.push({ id: acts[j].id, time: acts[j].time, type: acts[j].__typename, node: node });
    }
    completion(JSON.stringify({ ok: true, count: out.length, days: DAYS, notes: notes, activities: out }));
  } catch (err) {
    completion(JSON.stringify({ ok: false, error: String(err && err.message || err), notes: notes,
      url: location.href, headerNames: Object.keys(headers),
      windowKeys: Object.keys(window).filter(function (k) { return /apollo|token|auth|client|store/i.test(k); }).slice(0, 30) }));
  }
})();
