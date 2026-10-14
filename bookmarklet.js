// Readable source of the "Get Trackman token" bookmarklet.
// Run it while logged in at portal.trackmangolf.com. It only reads your own
// browser storage and shows the values so you can copy them. Nothing is sent anywhere.
(function () {
  var found = null, keys = [];
  [localStorage, sessionStorage].forEach(function (store) {
    for (var i = 0; i < store.length; i++) {
      var k = store.key(i), v = store.getItem(k);
      keys.push(k);
      if (found || !v || v.indexOf("refresh_token") < 0) continue;
      try {
        var o = JSON.parse(v);
        if (o.refresh_token) {
          var m = k.match(/^oidc\.user:[^:]+:\/\/[^:]+:(.+)$/);
          found = { client: (m && m[1]) || o.client_id || o.profile && o.profile.client_id || "", rt: o.refresh_token };
        }
      } catch (e) {}
    }
  });
  if (!found) {
    alert("No refresh token found. Storage keys:\n" + keys.join("\n"));
    return;
  }
  prompt("1 of 2: TRACKMAN_CLIENT_ID (copy this)", found.client || "not found, see storage keys");
  prompt("2 of 2: TRACKMAN_REFRESH_TOKEN (copy this)", found.rt);
})();
