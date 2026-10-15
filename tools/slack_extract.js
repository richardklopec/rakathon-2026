// Rakathon — pomocné funkce pro čtení Slacku a příloh PŘÍMO v přihlášené záložce app.slack.com
// Použití: v built-in browseru (záložka s app.slack.com) spustit celý soubor přes javascript_tool,
// pak volat např.  await window._dumpChannel('C0C82J7GGFJ')  nebo  await window._readFile('F0C9DRG1UDU').
// Token se bere z localStorage Slack klienta, nikam se neposílá mimo slack.com. Nic nezapisuje do Slacku.

(() => {
  const TEAM = 'T0C768CN5HU';
  const cfg = JSON.parse(localStorage.localConfig_v2);
  const tok = cfg.teams[TEAM].token;

  window._api = async (method, params = {}) => {
    const fd = new FormData();
    fd.append('token', tok);
    for (const k in params) fd.append(k, params[k]);
    return fetch('/api/' + method, { method: 'POST', body: fd, credentials: 'include' }).then(r => r.json());
  };

  const L = u => { let s = ''; for (let i = 0; i < u.length; i += 8192) s += String.fromCharCode.apply(null, u.subarray(i, i + 8192)); return s; };
  window._L = L;

  // tolerantní inflate (PDF streamy mají za koncem smetí → standardní DecompressionStream by spadl)
  window._inflate = async (bytes, fmt) => {
    const ds = new DecompressionStream(fmt);
    const w = ds.writable.getWriter(); w.write(bytes).catch(() => {}); w.close().catch(() => {});
    const rd = ds.readable.getReader(); const parts = []; let tot = 0;
    try { while (true) { const { done, value } = await rd.read(); if (done) break; parts.push(value); tot += value.length; } } catch (e) {}
    if (!tot) return null;
    const o = new Uint8Array(tot); let p = 0; for (const x of parts) { o.set(x, p); p += x.length; } return o;
  };

  window._getBytes = async id => {
    const r = await window._api('files.info', { file: id });
    const res = await fetch(r.file.url_private_download, { credentials: 'include' });
    return new Uint8Array(await res.arrayBuffer());
  };

  const fmtMsg = m => {
    let s = new Date(m.ts * 1000).toISOString().slice(5, 16) + ' [' + (m.user || m.bot_id) + '] ' + (m.text || '');
    if (m.reply_count) s += ` {replies:${m.reply_count} ts:${m.ts}}`;
    if (m.files) s += ' FILES: ' + m.files.map(f => `${f.name} (${f.filetype}) ${f.id}`).join(', ');
    if (m.attachments) s += ' ATT: ' + m.attachments.map(a => `${a.title || ''} ${a.from_url || a.title_link || ''} :: ${(a.text || '').slice(0, 500)}`).join(' | ');
    return s;
  };

  // celý kanál včetně všech vláken; vrací text
  window._dumpChannel = async (channel, { withThreads = true } = {}) => {
    let msgs = [], cursor;
    do {
      const r = await window._api('conversations.history', { channel, limit: '200', ...(cursor ? { cursor } : {}) });
      if (!r.ok) return 'ERR ' + r.error;
      msgs = msgs.concat(r.messages); cursor = r.response_metadata && r.response_metadata.next_cursor;
    } while (cursor);
    msgs = msgs.filter(m => m.subtype !== 'channel_join').reverse();
    let out = '';
    for (const m of msgs) {
      out += fmtMsg(m) + '\n';
      if (withThreads && m.reply_count) {
        const t = await window._api('conversations.replies', { channel, ts: m.ts, limit: '200' });
        out += t.messages.slice(1).map(x => '    ↳ ' + fmtMsg(x)).join('\n') + '\n';
      }
      out += '---\n';
    }
    return out;
  };

  window._listChannels = async () => {
    const r = await window._api('conversations.list', { limit: '1000', types: 'public_channel', exclude_archived: 'true' });
    return r.channels.map(c => `${c.id}  #${c.name}  (${c.num_members})  ${c.purpose && c.purpose.value || ''}`).join('\n');
  };

  // ---------- PPTX: slidy + poznámky řečníka ----------
  window._pptx = async id => {
    const b = await window._getBytes(id); const dv = new DataView(b.buffer);
    let e = b.length - 22; while (e > 0 && dv.getUint32(e, true) !== 0x06054b50) e--;
    const n = dv.getUint16(e + 10, true); let p = dv.getUint32(e + 16, true); const ents = [];
    for (let i = 0; i < n; i++) {
      const m = dv.getUint16(p + 10, true), cs = dv.getUint32(p + 20, true), fl = dv.getUint16(p + 28, true), el = dv.getUint16(p + 30, true), cl = dv.getUint16(p + 32, true), off = dv.getUint32(p + 42, true);
      ents.push({ name: new TextDecoder().decode(b.subarray(p + 46, p + 46 + fl)), m, cs, off }); p += 46 + fl + el + cl;
    }
    const out = {};
    for (const x of ents.filter(x => /^ppt\/(slides\/slide|notesSlides\/notesSlide)\d+\.xml$/.test(x.name))) {
      const st = x.off + 30 + dv.getUint16(x.off + 26, true) + dv.getUint16(x.off + 28, true);
      const raw = b.subarray(st, st + x.cs); const d = x.m === 0 ? raw : await window._inflate(raw, 'deflate-raw');
      const xml = new TextDecoder().decode(d);
      out[x.name] = xml.split(/<\/a:p>/).map(pp => [...pp.matchAll(/<a:t>([^<]*)<\/a:t>/g)].map(mm => mm[1]).join('')).filter(Boolean).join('\n');
    }
    const num = k => +k.match(/(\d+)\.xml/)[1];
    return Object.keys(out).sort((a, c) => (a.includes('notes') - c.includes('notes')) || num(a) - num(c))
      .map(k => '## ' + k.replace('ppt/', '') + '\n' + out[k]).join('\n')
      .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
  };

  // ---------- PDF: text po stránkách (Flate, ObjStm, ToUnicode, Form XObjects) ----------
  window._pdf = async id => {
    const b = await window._getBytes(id); const s = L(b); const objs = {};
    const re = /(\d+)\s+(\d+)\s+obj\b/g; let m; const starts = [];
    while ((m = re.exec(s))) starts.push([+m[1], m.index, re.lastIndex]);
    for (let i = 0; i < starts.length; i++) {
      const [n, , bodyStart] = starts[i]; let end = s.indexOf('endobj', bodyStart); if (end < 0) end = i + 1 < starts.length ? starts[i + 1][1] : s.length;
      let body = s.slice(bodyStart, end), stream = null; const si = body.search(/stream\r?\n/);
      if (si >= 0 && body.includes('endstream')) {
        const dict = body.slice(0, si); const off = bodyStart + si + body.slice(si).match(/stream\r?\n/)[0].length; const raw = b.subarray(off, s.indexOf('endstream', off));
        if (/FlateDecode/.test(dict)) stream = await window._inflate(raw, 'deflate'); else if (!/Filter/.test(dict)) stream = raw; body = dict;
      }
      objs[n] = { dict: body, stream };
    }
    for (const k in objs) { const o = objs[k]; if (/\/Type\s*\/ObjStm/.test(o.dict) && o.stream) { const txt = L(o.stream); const N = +o.dict.match(/\/N\s+(\d+)/)[1], F = +o.dict.match(/\/First\s+(\d+)/)[1]; const h = txt.slice(0, F).trim().split(/\s+/).map(Number); for (let j = 0; j < N; j++) { const on = h[2 * j], of = h[2 * j + 1], nx = j + 1 < N ? h[2 * j + 3] : txt.length - F; if (!objs[on]) objs[on] = { dict: txt.slice(F + of, F + nx), stream: null }; } } }
    const ref = (str, key) => { const mm = str.match(new RegExp('/' + key + '\\s*(\\d+)\\s+\\d+\\s+R')); return mm ? +mm[1] : null; };
    const dictOf = (str, key) => { const i = str.indexOf('/' + key); if (i < 0) return null; let j = i + key.length + 1; while (/\s/.test(str[j])) j++; if (str.startsWith('<<', j)) { let d = 0, k = j; for (; k < str.length; k++) { if (str.startsWith('<<', k)) { d++; k++; } else if (str.startsWith('>>', k)) { d--; k++; if (d === 0) break; } } return str.slice(j, k + 1); } const mm = str.slice(j).match(/^(\d+)\s+\d+\s+R/); return mm && objs[+mm[1]] ? objs[+mm[1]].dict : null; };
    const namesOf = d => { const r = {}; if (!d) return r; for (const mm of d.matchAll(/\/([^\s\/<>\[\]]+)\s+(\d+)\s+\d+\s+R/g)) r[mm[1]] = +mm[2]; return r; };
    const cache = {};
    const cmap = fn => { if (cache[fn]) return cache[fn]; const f = objs[fn], res = { map: {}, bytes: 1 }; if (f) { const tu = ref(f.dict, 'ToUnicode'); if (tu && objs[tu] && objs[tu].stream) { const t = L(objs[tu].stream); const cs = t.match(/begincodespacerange\s*<([0-9a-fA-F]+)>/); if (cs) res.bytes = cs[1].length / 2; const hex = hh => { let o = ''; for (let i = 0; i < hh.length; i += 4) o += String.fromCharCode(parseInt(hh.substr(i, 4), 16)); return o; }; for (const blk of t.matchAll(/beginbfchar([\s\S]*?)endbfchar/g)) for (const q of blk[1].matchAll(/<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]*)>/g)) res.map[parseInt(q[1], 16)] = hex(q[2]); for (const blk of t.matchAll(/beginbfrange([\s\S]*?)endbfrange/g)) for (const q of blk[1].matchAll(/<([0-9a-fA-F]+)>\s*<([0-9a-fA-F]+)>\s*(<[0-9a-fA-F]*>|\[[^\]]*\])/g)) { const a = parseInt(q[1], 16), z = parseInt(q[2], 16); if (q[3][0] === '<') { const base = q[3].slice(1, -1), head = base.slice(0, -4), last = parseInt(base.slice(-4), 16); for (let c = a; c <= z; c++) res.map[c] = hex(head) + String.fromCharCode(last + c - a); } else { const arr = [...q[3].matchAll(/<([0-9a-fA-F]*)>/g)]; for (let c = a; c <= z && c - a < arr.length; c++) res.map[c] = hex(arr[c - a][1]); } } } else if (/Identity-H/.test(f.dict)) res.bytes = 2; } return (cache[fn] = res); };
    const dec = (str, fn) => { const cm = fn != null ? cmap(fn) : { map: {}, bytes: 1 }; let o = ''; for (let i = 0; i < str.length; i += cm.bytes) { let c = 0; for (let k = 0; k < cm.bytes; k++) c = c * 256 + (str.charCodeAt(i + k) || 0); o += cm.map[c] !== undefined ? cm.map[c] : (cm.bytes === 1 ? String.fromCharCode(c) : ''); } return o; };
    const lit = (t, i) => { let d = 1, o = ''; i++; while (i < t.length && d > 0) { const c = t[i]; if (c === '\\') { const nn = t[i + 1], esc = { n: '\n', r: '\r', t: '\t', b: '\b', f: '\f', '(': '(', ')': ')', '\\': '\\' }; if (esc[nn] !== undefined) { o += esc[nn]; i += 2; continue; } if (/[0-7]/.test(nn)) { const oc = t.substr(i + 1, 3).match(/^[0-7]{1,3}/)[0]; o += String.fromCharCode(parseInt(oc, 8)); i += 1 + oc.length; continue; } i += 2; continue; } if (c === '(') d++; if (c === ')') { d--; if (d === 0) { i++; break; } } o += c; i++; } return [o, i]; };
    const run = (t, fonts, xo, depth) => { let out = '', cur = null, i = 0, lastY = null; const st = [];
      while (i < t.length) { const c = t[i]; if (/\s/.test(c)) { i++; continue; } if (c === '%') { while (i < t.length && t[i] !== '\n') i++; continue; }
        if (c === '(') { const [x, ni] = lit(t, i); st.push({ s: x }); i = ni; continue; }
        if (c === '<' && t[i + 1] !== '<') { const e2 = t.indexOf('>', i), h = t.slice(i + 1, e2).replace(/\s/g, ''); let x = ''; for (let k = 0; k < h.length; k += 2) x += String.fromCharCode(parseInt((h.substr(k, 2) + '0').slice(0, 2), 16)); st.push({ s: x }); i = e2 + 1; continue; }
        if (c === '[') { st.push('['); i++; continue; } if (c === ']') { const arr = []; while (st.length && st[st.length - 1] !== '[') arr.unshift(st.pop()); st.pop(); st.push({ arr }); i++; continue; }
        if (c === '/') { let j = i + 1; while (j < t.length && !/[\s\(\)\[\]<>\/%]/.test(t[j])) j++; st.push(t.slice(i, j)); i = j; continue; }
        let j = i; while (j < t.length && !/[\s\(\)\[\]<>\/%]/.test(t[j])) j++; if (j === i) { i++; continue; } const w = t.slice(i, j); i = j;
        if (/^[-+]?\d*\.?\d+$/.test(w)) { st.push(+w); continue; }
        const fn = cur != null ? fonts[cur] : null;
        if (w === 'Tf') { const f = st[st.length - 2]; cur = typeof f === 'string' ? f.slice(1) : null; }
        else if (w === 'Tj' || w === "'" || w === '"') { const a = st[st.length - 1]; if (w !== 'Tj') out += '\n'; if (a && a.s !== undefined) out += dec(a.s, fn); }
        else if (w === 'TJ') { const a = st[st.length - 1]; if (a && a.arr) for (const x of a.arr) { if (x && x.s !== undefined) out += dec(x.s, fn); else if (typeof x === 'number' && x < -200) out += ' '; } }
        else if (w === 'Td' || w === 'TD') out += Math.abs(st[st.length - 1]) > 1 ? '\n' : ' ';
        else if (w === 'Tm') { const y = st[st.length - 1]; out += (lastY === null || Math.abs(y - lastY) > 1) ? '\n' : ' '; lastY = y; }
        else if (w === 'T*' || w === 'ET') out += '\n';
        else if (w === 'Do' && depth < 3) { const nm = st[st.length - 1]; const xn = typeof nm === 'string' ? xo[nm.slice(1)] : null; const x = xn != null && objs[xn]; if (x && /\/Subtype\s*\/Form/.test(x.dict) && x.stream) { const r = dictOf(x.dict, 'Resources') || ''; out += run(L(x.stream), Object.assign({}, fonts, namesOf(dictOf(r, 'Font'))), namesOf(dictOf(r, 'XObject')), depth + 1); } }
        st.length = 0; }
      return out; };
    const pages = []; const visit = n => { const o = objs[n]; if (!o) return; if (/\/Type\s*\/Pages/.test(o.dict)) { const k = o.dict.match(/\/Kids\s*\[([^\]]*)\]/); if (k) for (const mm of k[1].matchAll(/(\d+)\s+\d+\s+R/g)) visit(+mm[1]); } else pages.push(n); };
    const root = Object.keys(objs).find(k => /\/Type\s*\/Catalog/.test(objs[k].dict)); if (root) visit(ref(objs[root].dict, 'Pages'));
    let text = '';
    pages.forEach((pn, idx) => { const p = objs[pn]; let rs = dictOf(p.dict, 'Resources'); if (!rs) { const par = ref(p.dict, 'Parent'); rs = par && objs[par] ? dictOf(objs[par].dict, 'Resources') : ''; } rs = rs || ''; let cs = []; const ca = p.dict.match(/\/Contents\s*\[([^\]]*)\]/); if (ca) cs = [...ca[1].matchAll(/(\d+)\s+\d+\s+R/g)].map(x => +x[1]); else { const c1 = ref(p.dict, 'Contents'); if (c1 != null) cs = [c1]; } let pt = ''; for (const c of cs) if (objs[c] && objs[c].stream) pt += run(L(objs[c].stream), namesOf(dictOf(rs, 'Font')), namesOf(dictOf(rs, 'XObject')), 0); text += '\n=== PAGE ' + (idx + 1) + ' ===\n' + pt.replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim(); });
    return text;
  };

  // univerzální čtečka přílohy podle typu
  window._readFile = async id => {
    const r = await window._api('files.info', { file: id }); const f = r.file;
    if (f.filetype === 'pptx') return await window._pptx(id);
    if (f.filetype === 'pdf') return await window._pdf(id);
    if (f.plain_text || f.preview) return f.plain_text || f.preview;
    if (/^(text|csv|json|md|markdown|python|javascript)$/.test(f.filetype)) return new TextDecoder().decode(await window._getBytes(id));
    return `NEPODPOROVANÝ TYP ${f.filetype} (${f.name}, ${f.size} B) — zvážit stažení se souhlasem uživatele`;
  };

  return 'slack_extract ready';
})();
