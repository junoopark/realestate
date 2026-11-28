/* dc-lite: 디자인 캔버스(.dc.html) 화면을 일반 웹페이지에서 돌리는 작은 실행기 (KHMI AI 프로토타입용) */
(function () {
  function DCLogic(props) { this.props = props || {}; this.state = {}; }
  DCLogic.prototype.setState = function (p, cb) {
    var patch = typeof p === 'function' ? p(this.state, this.props) : p;
    this.state = Object.assign({}, this.state, patch);
    schedule(); if (cb) setTimeout(cb, 0);
  };
  DCLogic.prototype.forceUpdate = function () { schedule(); };
  window.DCLogic = DCLogic;

  var HOLE = /\{\{\s*([^}]+?)\s*\}\}/g, WHOLE = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;
  var EVT = { onClick: 'click', onChange: 'change', onInput: 'input', onKeyDown: 'keydown', onSubmit: 'submit', onFocus: 'focus',
    onMouseEnter: 'mouseenter', onMouseLeave: 'mouseleave', onMouseMove: 'mousemove' };
  function lookup(path, scope) {
    if (path === 'true') return true; if (path === 'false') return false; if (path === 'null') return null;
    if (/^-?\d+(\.\d+)?$/.test(path)) return +path;
    if (/^'.*'$|^".*"$/.test(path)) return path.slice(1, -1);
    var parts = path.split('.'), v = scope;
    for (var i = 0; i < parts.length; i++) { if (v == null) return undefined; v = v[parts[i]]; }
    return v;
  }
  function interp(str, scope) { return str.replace(HOLE, function (_, p) { var v = lookup(p, scope); return v == null ? '' : String(v); }); }
  function bindEvent(el, name, fn) {
    var type = EVT[name] || name.slice(2).toLowerCase();
    var tag = el.tagName;
    if (name === 'onChange' && (tag === 'TEXTAREA' || (tag === 'INPUT' && !/^(checkbox|radio)$/.test(el.type)))) type = 'input';
    el.__dc = el.__dc || {}; el.__dc[type] = fn;
  }
  function process(node, scope) {
    if (node.nodeType === 3) { if (node.nodeValue.indexOf('{{') >= 0) node.nodeValue = interp(node.nodeValue, scope); return; }
    if (node.nodeType !== 1) return;
    var tag = node.localName;
    var sc = tag === 'template' ? node.getAttribute('data-sc') : null;
    if (sc === 'for') {
      var m = WHOLE.exec(node.getAttribute('list') || ''), list = m ? lookup(m[1], scope) : [], as = node.getAttribute('as') || 'item';
      var frag = document.createDocumentFragment();
      (list || []).forEach(function (item, i) {
        var s = Object.create(scope); s[as] = item; s.$index = i;
        var c = node.content.cloneNode(true); var kids = Array.prototype.slice.call(c.childNodes);
        kids.forEach(function (k) { frag.appendChild(k); process(k, s); });
      });
      node.parentNode.replaceChild(frag, node); return;
    }
    if (sc === 'if') {
      var mm = WHOLE.exec(node.getAttribute('value') || ''), ok = mm ? lookup(mm[1], scope) : false;
      if (ok) { var c2 = node.content.cloneNode(true), kids2 = Array.prototype.slice.call(c2.childNodes), f2 = document.createDocumentFragment(); kids2.forEach(function (k) { f2.appendChild(k); process(k, scope); }); node.parentNode.replaceChild(f2, node); }
      else node.parentNode.removeChild(node);
      return;
    }
    Array.prototype.slice.call(node.attributes).forEach(function (a) {
      var n = a.name, v = a.value;
      if (n.indexOf('hint-') === 0) { node.removeAttribute(n); return; }
      if (v.indexOf('{{') < 0) return;
      var w = WHOLE.exec(v);
      var real = n; // 속성 이름은 소문자로 들어옴
      var evName = Object.keys(EVT).filter(function (k) { return k.toLowerCase() === n; })[0];
      if (w && evName) { node.removeAttribute(n); var fn = lookup(w[1], scope); if (typeof fn === 'function') bindEvent(node, evName, fn); return; }
      var val = w ? lookup(w[1], scope) : interp(v, scope);
      if (n === 'value' && (tag === 'select' || tag === 'input' || tag === 'textarea')) {
        node.removeAttribute(n); node.__val = val == null ? '' : String(val);
        if (tag === 'input') node.setAttribute('value', node.__val);
        return;
      }
      if (val == null || val === false) node.removeAttribute(real); else node.setAttribute(real, String(val));
    });
    Array.prototype.slice.call(node.childNodes).forEach(function (k) { process(k, scope); });
    if (tag === 'textarea' && node.__val != null) node.value = node.__val;
    if (tag === 'select' && node.__val != null) Array.prototype.forEach.call(node.options, function (o) { if (o.value === node.__val) o.setAttribute('selected', ''); else o.removeAttribute('selected'); });
  }
  // 템플릿 안의 <template> 대체: sc-for 안 내용도 그대로 복제되도록 x-dc 원본을 보관
  var root, tpl, comp, pending = false, composing = false;
  function build() {
    var vals = comp.renderVals() || {};
    var box = document.createElement('div');
    box.appendChild(tpl.content.cloneNode(true));
    Array.prototype.slice.call(box.childNodes).forEach(function (k) { process(k, vals); });
    return box;
  }
  function copyDc(from, to) {
    from.__dc = to.__dc;
    if (from.tagName === 'SELECT' && to.__val != null) from.value = to.__val;
  }
  function render() {
    pending = false;
    var box = build();
    if (!root.firstChild) { while (box.firstChild) root.appendChild(box.firstChild); syncSelects(root); return; }
    morphdom(root, box, {
      childrenOnly: true,
      onBeforeElUpdated: function (fromEl, toEl) {
        copyDc(fromEl, toEl);
        if ((fromEl.tagName === 'TEXTAREA' || fromEl.tagName === 'INPUT') && fromEl === document.activeElement && composing) toEl.value = fromEl.value;
        else if (fromEl.tagName === 'TEXTAREA' && toEl.__val != null) toEl.value = toEl.__val;
        return true;
      }
    });
    syncSelects(root);
  }
  function syncSelects(r) { Array.prototype.forEach.call(r.querySelectorAll('select'), function (s) { var o = s.querySelector('option[selected]'); if (o && s.value !== o.value) s.value = o.value; }); }
  function schedule() { if (!pending) { pending = true; requestAnimationFrame(render); } }
  function shim(e, el) {
    return { type: e.type, target: e.target, currentTarget: el, clientX: e.clientX, clientY: e.clientY, key: e.key, keyCode: e.keyCode, shiftKey: e.shiftKey,
      nativeEvent: e, preventDefault: function () { e.preventDefault(); }, stopPropagation: function () { e.stopPropagation(); } };
  }
  function find(start, type) { var n = start; while (n && n !== root) { if (n.__dc && n.__dc[type]) return n; n = n.parentNode; } return null; }
  function delegate() {
    ['click', 'change', 'input', 'keydown', 'submit', 'mousemove'].forEach(function (t) {
      root.addEventListener(t, function (e) {
        if (t === 'input' && e.isComposing) return;
        var el = find(e.target, t); if (el) el.__dc[t](shim(e, el));
      });
    });
    root.addEventListener('focusin', function (e) { var el = find(e.target, 'focus'); if (el) el.__dc.focus(shim(e, el)); });
    root.addEventListener('mouseover', function (e) {
      var el = find(e.target, 'mouseenter');
      if (el && !(e.relatedTarget && el.contains(e.relatedTarget))) el.__dc.mouseenter(shim(e, el));
    });
    root.addEventListener('mouseout', function (e) {
      var n = e.target;
      while (n && n !== root) {
        if (n.__dc && n.__dc.mouseleave && !(e.relatedTarget && n.contains(e.relatedTarget))) n.__dc.mouseleave(shim(e, n));
        n = n.parentNode;
      }
    });
    root.addEventListener('compositionstart', function () { composing = true; });
    root.addEventListener('compositionend', function (e) {
      composing = false; var el = find(e.target, 'input'); if (el) el.__dc.input(shim(e, el));
    });
  }
  window.dcMount = function (Component) {
    root = document.getElementById('dc-root'); tpl = document.getElementById('dc-tpl');
    comp = new Component({});
    delegate(); render();
    if (comp.componentDidMount) comp.componentDidMount();
    window.addEventListener('pagehide', function () { if (comp.componentWillUnmount) comp.componentWillUnmount(); });
  };
})();
