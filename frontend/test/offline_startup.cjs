// Run after serving build/web on 127.0.0.1:8080. No npm dependencies needed.
const { spawn } = require('node:child_process');
const { mkdtempSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const profile = mkdtempSync(join(tmpdir(), 'biometric-offline-smoke-'));
const chrome = process.env.CHROME_PATH ||
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const child = spawn(chrome, [
  '--headless=new', '--no-first-run', '--no-default-browser-check',
  '--disable-background-networking', '--no-proxy-server',
  '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1',
  `--user-data-dir=${profile}`, '--virtual-time-budget=20000',
  '--dump-dom', 'http://127.0.0.1:8080/',
], { windowsHide: true });
let html = '';
let errors = '';
child.stdout.on('data', data => html += data);
child.stderr.on('data', data => errors += data);
const timeout = setTimeout(() => {
  child.kill();
  console.error('Browser startup timed out.');
  process.exitCode = 1;
}, 45000);
child.on('error', error => {
  clearTimeout(timeout);
  console.error(error.message);
  process.exitCode = 1;
});
child.on('close', code => {
  clearTimeout(timeout);
  const rendered = html.includes('flt-glass-pane') && !html.includes('id="startup"');
  console.log(`Local Flutter first frame with external DNS blocked: ${rendered ? 'PASS' : 'FAIL'}`);
  console.log(`Isolated browser profile: ${profile}`);
  if (!rendered || code !== 0) {
    console.error(errors.slice(-3000));
    process.exitCode = 1;
  }
});
