(function () {
  // Evita que corra dentro de la pantalla de llamada
  if (window.location.pathname.startsWith('/call/') && window.location.pathname !== '/call/') return;

  // Evita duplicados si el script se carga dos veces
  if (document.getElementById('incall-global')) return;

  const banner = document.createElement('div');
  banner.id = 'incall-global';
  banner.style.cssText =
    'display:none;position:fixed;top:0;left:0;right:0;padding:12px;' +
    'background:#12304f;color:#fff;z-index:9999;align-items:center;' +
    'justify-content:space-between;gap:8px;font-family:sans-serif;';
  banner.innerHTML =
    '<b id="icName">Llamada entrante...</b>' +
    '<span>' +
    '<button id="btnDecline" style="margin-right:6px;padding:6px 12px;">Rechazar</button>' +
    '<button id="btnAnswer" style="padding:6px 12px;">Contestar</button>' +
    '</span>';
  document.body.appendChild(banner);

  let currentCall = null;

  function post(path, body) {
    return fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  async function check() {
    try {
      const r = await fetch('/api/calls/pending/', { credentials: 'same-origin' });
      if (r.ok) {
        const data = await r.json();
        currentCall = data.call;
        if (currentCall) {
          banner.querySelector('#icName').textContent = 'Llamada de ' + currentCall.name;
          banner.style.display = 'flex';
        } else {
          banner.style.display = 'none';
        }
      }
    } catch (e) { /* reintenta en el próximo ciclo */ }
    setTimeout(check, 2000);
  }
  check();

  banner.querySelector('#btnAnswer').onclick = function () {
    if (currentCall) window.location.href = '/call/' + currentCall.id + '/';
  };

  banner.querySelector('#btnDecline').onclick = async function () {
    if (currentCall) await post('/api/calls/' + currentCall.id + '/state/', { estado: 'RE' });
    banner.style.display = 'none';
    currentCall = null;
  };
})();