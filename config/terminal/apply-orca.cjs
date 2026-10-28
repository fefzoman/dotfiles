const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { DatabaseSync, backup } = require('node:sqlite');

async function apply(database, profileId, updates) {
  const chunks = '/Applications/Orca.app/Contents/Resources/app.asar.unpacked/out/main/chunks';
  const file = fs.readdirSync(chunks).find(name => name.startsWith('profile-state-sqlite-authority-'));
  const { t: Authority } = require(path.join(chunks, file));
  if (typeof Authority?.prototype?.writeSerializedDomains !== 'function') {
    throw new Error('This Orca version is unsupported. No settings changed.');
  }
  const authority = new Authority(database, profileId);
  try {
    const state = JSON.parse(authority.readSerializedState());
    const themes = state.settings.terminalCustomThemes ?? [];
    const ids = new Set(updates.terminalCustomThemes.map(theme => theme.id));
    const settings = { ...state.settings, ...updates, terminalCustomThemes: [
      ...themes.filter(theme => !ids.has(theme.id)), ...updates.terminalCustomThemes
    ] };
    const source = new DatabaseSync(database, { readOnly: true });
    try {
      const destination = `${database}.bak.${Date.now()}`;
      fs.closeSync(fs.openSync(destination, 'wx', 0o600));
      await backup(source, destination);
    } finally {
      source.close();
    }
    authority.writeSerializedDomains([{ domain: 'settings', payload: JSON.stringify(settings) }]);
  } finally {
    authority.close();
  }
}

if (require.main === module) {
  const running = spawnSync('pgrep', ['-x', 'Orca']);
  if (running.status !== 1) {
    console.error('Quit Orca before running this command. No settings changed.');
    process.exitCode = 1;
  } else {
    const profileId = 'local-default';
    const database = path.join(os.homedir(), 'Library/Application Support/orca/profiles', profileId, 'profile-state.db');
    apply(database, profileId, require('./orca.json')).then(() => {
      console.log('Applied Alacritty styling. Open Orca to use it.');
    }).catch(error => { console.error(error.message); process.exitCode = 1; });
  }
}

module.exports = { apply };
