(function () {
  var params = new URLSearchParams(window.location.search);
  var encoded = params.get('qn_pwd');
  if (!encoded) {
    return;
  }

  var password;
  try {
    var normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
    var padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);
    password = atob(padded);
  } catch (error) {
    return;
  }

  if (params.has('qn_pwd')) {
    params.delete('qn_pwd');
    var nextQuery = params.toString();
    var nextUrl =
      window.location.pathname +
      (nextQuery ? '?' + nextQuery : '') +
      window.location.hash;
    window.history.replaceState(null, '', nextUrl);
  }

  var handledButtons = new WeakSet();

  function visible(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  }

  function clickMatching(matchText) {
    var nodes = document.querySelectorAll('button, a, [role="button"], input[type="submit"], input[type="button"]');
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (!visible(node) || handledButtons.has(node)) {
        continue;
      }
      var label = (node.textContent || node.value || '').replace(/\s+/g, ' ').trim();
      if (!matchText(label)) {
        continue;
      }
      handledButtons.add(node);
      node.click();
      return true;
    }
    return false;
  }

  function pageText() {
    return (document.body && document.body.innerText) || '';
  }

  function autoConfirmFingerprint() {
    var text = pageText();
    if (!/recognize this server|fingerprint has changed|Verify server fingerprint/i.test(text)) {
      return;
    }
    clickMatching(function (label) {
      return /^(Yes, I do|I'm aware of the change)$/i.test(label);
    });
  }

  function autoSubmitPassword() {
    var text = pageText();
    if (!/Provide password|requesting for your password|Authenticate/i.test(text)) {
      return;
    }
    var inputs = document.querySelectorAll('input[type="password"]');
    for (var i = 0; i < inputs.length; i++) {
      var input = inputs[i];
      if (!visible(input) || input.value) {
        continue;
      }
      input.focus();
      input.value = password;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      window.setTimeout(function () {
        clickMatching(function (label) {
          return /^Authenticate$/i.test(label);
        });
      }, 120);
      return;
    }
  }

  window.setInterval(function () {
    autoConfirmFingerprint();
    autoSubmitPassword();
  }, 350);
})();
