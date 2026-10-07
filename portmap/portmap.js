// LDP port map renderer - shared by the plugin's Port Map page and
// tools/make_port_map.py. Builds DOM with textContent only (map data is never
// treated as HTML). Data shape: see make_port_map.py build_data().
window.LDPPortMap = (function () {
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = String(text);
    return e;
  }
  function plural(n, word) { return n + ' ' + word + (n === 1 ? '' : 's'); }

  function nullRow(n, where) {
    var li = el('li', 'pm-null');
    li.appendChild(el('span', 'pm-n', '∅'));
    var nm = el('span', 'pm-nm', plural(n, 'null pixel'));
    nm.appendChild(el('small', null, where));
    li.appendChild(nm);
    li.appendChild(el('span', 'pm-px', n));
    return li;
  }

  function portCard(p) {
    if (!p.props || !p.props.length) {
      var e = el('div', 'pm-port pm-empty');
      var h = el('div', 'pm-ph');
      h.appendChild(el('b', null, 'Port ' + p.port));
      h.appendChild(el('span', null, 'empty'));
      e.appendChild(h);
      return e;
    }
    var nulls = 0, total = 0;
    p.props.forEach(function (x) { nulls += (x.null || 0) + (x.endnull || 0); total += x.pixels || 0; });
    total += nulls;
    var card = el('div', 'pm-port');
    var ph = el('div', 'pm-ph');
    ph.appendChild(el('b', null, 'Port ' + p.port));
    if (p.remote) { ph.appendChild(document.createTextNode(' ')); ph.appendChild(el('em', null, 'Receiver ' + p.remote)); }
    ph.appendChild(el('span', null, plural(p.props.length, 'prop') + ' · ' + total + ' px' + (nulls ? ' (' + nulls + ' null)' : '')));
    card.appendChild(ph);
    var ol = el('ol');
    p.props.forEach(function (x, i) {
      if (x.null) ol.appendChild(nullRow(x.null, 'before ' + x.name));
      var li = el('li');
      li.appendChild(el('span', 'pm-n', i + 1));
      var nm = el('span', 'pm-nm', x.name);
      if (x.notes && x.notes.length) nm.appendChild(el('small', null, x.notes.join(' · ')));
      li.appendChild(nm);
      li.appendChild(el('span', 'pm-px', x.pixels));
      ol.appendChild(li);
      if (x.endnull) ol.appendChild(nullRow(x.endnull, 'after ' + x.name));
    });
    card.appendChild(ol);
    return card;
  }

  function dmxCard(list) {
    var card = el('div', 'pm-port');
    var ph = el('div', 'pm-ph');
    ph.appendChild(el('b', null, 'DMX'));
    ph.appendChild(el('span', null, plural(list.length, 'fixture')));
    card.appendChild(ph);
    var ul = el('ul');
    list.forEach(function (d) {
      var li = el('li');
      li.appendChild(el('span', 'pm-nm', d.name));
      var ch = Number(d.ch), w = Number(d.width) || 1;
      li.appendChild(el('span', 'pm-px', 'DMX ' + d.ch + (isFinite(ch) && w > 1 ? '–' + (ch + w - 1) : '')));
      ul.appendChild(li);
    });
    card.appendChild(ul);
    return card;
  }

  function render(data, root) {
    root.textContent = '';
    root.classList.add('ldp-pm');
    root.appendChild(el('h1', null, data.title || 'Port Map'));
    root.appendChild(el('p', 'pm-meta', 'From xLights show ' + (data.show || '?') + ' · generated ' + (data.generated || '?') +
      ' · props in wiring order (1 = closest to the controller); ∅ = null pixels, wire them in exactly where shown'));
    if (data.unassigned && data.unassigned.length)
      root.appendChild(el('p', 'pm-warn', 'Not assigned to a controller: ' + data.unassigned.join(', ')));
    (data.controllers || []).forEach(function (c) {
      var sec = el('section');
      sec.appendChild(el('h2', null, c.name));
      sec.appendChild(el('p', 'pm-sub', [((c.vendor || '') + ' ' + (c.model || '')).trim(), c.ip, (c.pixels || 0) + ' px'].filter(Boolean).join(' · ')));
      var grid = el('div', 'pm-grid');
      (c.ports || []).forEach(function (p) { grid.appendChild(portCard(p)); });
      if (c.dmx && c.dmx.length) grid.appendChild(dmxCard(c.dmx));
      sec.appendChild(grid);
      root.appendChild(sec);
    });
  }

  function valid(d) {
    return d && typeof d === 'object' && Array.isArray(d.controllers);
  }

  return { render: render, valid: valid };
})();
