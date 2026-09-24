(() => {
  let started = false;
  window.showStartupFailure = () => {
    if (started) return;
    document.getElementById('startup-title').textContent = 'Unable to finish loading';
    document.getElementById('startup-detail').textContent =
      'Keep the local web server running and reload. Internet is not required for the bundled build. If this persists, rebuild using the offline instructions.';
    document.getElementById('startup-retry').hidden = false;
  };
  document.getElementById('startup-retry').addEventListener('click', () => location.reload());
  const timeout = setTimeout(window.showStartupFailure, 30000);
  window.addEventListener('flutter-first-frame', () => {
    started = true;
    clearTimeout(timeout);
    document.getElementById('startup').remove();
  }, { once: true });
})();
