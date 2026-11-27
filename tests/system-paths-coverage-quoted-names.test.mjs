/**
 * system-paths-coverage-quoted-names.test.mjs - the SYSTEM_PATHS coverage
 * guard must read file names the way git stores them, not the way git
 * prints them for a terminal.
 *
 * Plain `git ls-files` applies core.quotePath: any path with a byte outside
 * printable ASCII (a curly apostrophe, an accented letter) is printed wrapped
 * in double quotes with octal escapes. The guard used to split that output on
 * newlines and prefix-match it, so `"providers/caf\303\251.mjs"` matched no
 * registered prefix and a correctly registered file was reported as a
 * coverage gap, failing the whole suite.
 *
 * Driven against a throwaway git repo holding copies of the two scripts, the
 * same shape as the end-to-end case in updater-local-paths.test.mjs.
 */

import { mkdtempSync, mkdirSync, writeFileSync, copyFileSync } from 'fs';
import { spawnSync } from 'child_process';
import { tmpdir } from 'os';
import { join } from 'path';
import { ROOT, pass, fail, rmSync } from './helpers.mjs';

const dir = mkdtempSync(join(tmpdir(), 'co-coverage-quoted-'));
try {
  // Neutralize ambient git config (see updater-local-paths.test.mjs), then pin
  // core.quotePath on so the test reproduces the quoting even on a machine
  // whose global config turned it off.
  const env = { ...process.env, GIT_CONFIG_COUNT: '0', GIT_CONFIG_NOSYSTEM: '1' };
  const g = (...args) => spawnSync('git', args, { cwd: dir, encoding: 'utf-8', env });

  g('init', '-q', '-b', 'main', '.');
  g('config', 'user.email', 'test@example.com');
  g('config', 'user.name', 'Test');
  g('config', 'commit.gpgsign', 'false');
  g('config', 'core.hooksPath', join(dir, 'no-such-hooks'));
  g('config', 'core.quotePath', 'true');

  for (const f of ['validate-system-paths-coverage.mjs', 'update-system.mjs']) {
    copyFileSync(join(ROOT, f), join(dir, f));
  }

  // providers/ is a SYSTEM_PATHS directory prefix. A curly apostrophe
  // (U+2019) and an accented letter (U+00E9) are the two cases seen in
  // practice; both are quoted by git.
  const registered = ['providers/café.mjs', 'providers/Facebook’s feed.mjs'];
  mkdirSync(join(dir, 'providers'), { recursive: true });
  for (const f of registered) writeFileSync(join(dir, f), '// fixture\n');
  g('add', '-A');
  g('commit', '-qm', 'base');

  const runGuard = () =>
    spawnSync(process.execPath, [join(dir, 'validate-system-paths-coverage.mjs')], {
      cwd: dir,
      encoding: 'utf-8',
      env,
    });

  // Sanity: the fixture really does exercise quoting, or the next assertion
  // proves nothing.
  const listed = g('ls-files').stdout;
  if (listed.includes('"providers/caf\\303\\251.mjs"')) {
    pass('fixture: git quotes the non-ASCII names in plain ls-files output');
  } else {
    fail(`fixture does not reproduce core.quotePath quoting: ${JSON.stringify(listed)}`);
  }

  const covered = runGuard();
  if (covered.status === 0) {
    pass('registered files with non-ASCII names are covered (not a false coverage gap)');
  } else {
    fail(`guard reported a gap for registered non-ASCII names: status=${covered.status}\n${covered.stderr || covered.stdout}`);
  }

  // The fix must not turn the guard into a pass-everything: an unregistered
  // non-ASCII file is still a gap, and it is named as git stores it.
  const orphan = 'naïve-orphan.txt';
  writeFileSync(join(dir, orphan), 'orphan\n');
  g('add', '-A');
  g('commit', '-qm', 'orphan');
  const gap = runGuard();
  if (gap.status !== 0 && (gap.stderr || '').includes(orphan)) {
    pass('an unregistered non-ASCII file is still a coverage gap, reported by its real name');
  } else {
    fail(`expected a coverage gap naming ${orphan}, got status=${gap.status}\n${gap.stderr || gap.stdout}`);
  }
} finally {
  rmSync(dir, { recursive: true, force: true });
}
