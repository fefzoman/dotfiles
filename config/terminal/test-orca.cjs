const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { test } = require('node:test');
const { spawnSync } = require('node:child_process');
const { apply } = require('./apply-orca.cjs');

test('Orca style preserves other settings, themes and domains, with a backup', async () => {
  const chunks = '/Applications/Orca.app/Contents/Resources/app.asar.unpacked/out/main/chunks';
  const file = fs.readdirSync(chunks).find(name => name.startsWith('profile-state-sqlite-authority-'));
  const { t: Authority } = require(path.join(chunks, file));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'orca-style-'));
  const database = path.join(dir, 'profile-state.db');
  const settings = { untouched: true, terminalCustomThemes: [{ id: 'manual:existing' }] };
  const authority = new Authority(database, 'test');
  try {
    authority.readSerializedState();
    authority.writeSerializedDomains([
      { domain: 'settings', payload: JSON.stringify(settings) },
      { domain: 'repos', payload: '[{"id":"keep"}]' }
    ]);
    await apply(database, 'test', require('./orca.json'));
    const result = JSON.parse(authority.readSerializedState());
    assert.equal(result.settings.untouched, true);
    assert.equal(result.settings.terminalFontWeight, 100);
    assert.equal(result.settings.terminalFontWeightBold, 500);
    assert.deepEqual(result.settings.terminalCustomThemes[0], settings.terminalCustomThemes[0]);
    assert.deepEqual(result.repos, [{ id: 'keep' }]);
    const saved = fs.readdirSync(dir).find(name => name.includes('.bak.'));
    assert.ok(saved);
    assert.equal(fs.statSync(path.join(dir, saved)).mode & 0o777, 0o600);
    const snapshot = new Authority(path.join(dir, saved), 'test');
    try {
      assert.deepEqual(JSON.parse(snapshot.readSerializedState()).settings, settings);
    } finally {
      snapshot.close();
    }
    await apply(database, 'test', require('./orca.json'));
    assert.deepEqual(JSON.parse(authority.readSerializedState()), result);
  } finally {
    authority.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('CLI refuses to write when it cannot confirm Orca is closed', () => {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'apply-orca.cjs')], {
    env: { ...process.env, PATH: '' }, encoding: 'utf8'
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /Quit Orca/);
});
