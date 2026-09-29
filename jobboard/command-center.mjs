/**
 * command-center.mjs - the job board's bridge to command-center/ and resume/
 *
 * FORK-LOCAL (jobboard/ is declared in config/local-paths.txt).
 *
 * The command center's tracker notes (command-center/03-Pipeline/{Active,Archive}/
 * **.md, schema in 03-Pipeline/_Application-Schema.md) are the single source of
 * truth for real applications: the daily Gmail sync appends to their timelines
 * and pipeline_views.py builds the board and stats from their frontmatter. The
 * job board therefore:
 *
 *   - reads every tracker and links it to a board job when one of its `links`
 *     is that job's posting (same requisition-id matching as the merge);
 *   - derives a linked job's status from the tracker's `stage` instead of its
 *     own state, so the two can never disagree;
 *   - writes a new schema-compliant tracker when you confirm an application,
 *     and never edits or overwrites an existing note.
 *
 * The frontmatter reader mirrors 03-Pipeline/tracker_frontmatter.py (top-level
 * scalars, inline or block lists) so both sides read notes identically.
 *
 * It also discovers resume/<track>/<length>/*.pdf variants and the career-ops
 * evaluation reports (reports/*.md `**URL:**` / `**Score:**` headers).
 */

import { existsSync, readdirSync, readFileSync, realpathSync, statSync, writeFileSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { basename, dirname, join, relative, sep } from 'node:path';
import { isNestedCheckout } from '../lib/mjs-files.mjs';

export const TRACKER_STAGES = ['sourced', 'applied', 'recruiter', 'OA', 'phone', 'onsite', 'offer', 'rejected', 'withdrawn', 'ghosted'];

const STAGE_STATUS = {
  sourced: 'Saved',
  applied: 'Applied',
  recruiter: 'Applied',
  oa: 'Applied',
  phone: 'Interviewing',
  onsite: 'Interviewing',
  offer: 'Offer',
  rejected: 'Rejected',
  ghosted: 'Rejected',
  withdrawn: 'Not Interested',
};

/** Board status for a tracker stage; unknown stages count as Applied (a tracker exists). */
export function stageToStatus(stage) {
  return STAGE_STATUS[String(stage || '').trim().toLowerCase()] || 'Applied';
}

// ── Frontmatter (mirror of tracker_frontmatter.py) ─────────────────────────

const KEY_RE = /^([A-Za-z_][\w-]*)\s*:\s*(.*)$/;
const ITEM_RE = /^\s+-\s+(.*)$/;

function fmLines(text) {
  if (!text.startsWith('---\n')) return [];
  const end = text.indexOf('\n---', 4);
  return (end < 0 ? '' : text.slice(4, end)).split('\n');
}

const unquote = (s) => s.trim().replace(/^"+|"+$/g, '').replace(/^'+|'+$/g, '');

export function readFrontmatter(text) {
  const fm = {};
  for (const line of fmLines(text)) {
    const m = line.match(KEY_RE);
    if (m) fm[m[1]] = unquote(m[2]);
  }
  return fm;
}

export function readList(text, key) {
  const lines = fmLines(text);
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(KEY_RE);
    if (!m || m[1] !== key) continue;
    const inline = m[2].trim();
    if (inline) return inline.replace(/^[[\]]+|[[\]]+$/g, '').split(',').map(unquote).filter(Boolean);
    const items = [];
    for (const next of lines.slice(i + 1)) {
      const item = next.match(ITEM_RE);
      if (!item) break;
      if (unquote(item[1])) items.push(unquote(item[1]));
    }
    return items;
  }
  return [];
}

// ── Locations ──────────────────────────────────────────────────────────────

export function commandCenterPaths(root) {
  const dir = process.env.JOBBOARD_COMMAND_CENTER || join(root, 'command-center');
  const pipeline = join(dir, '03-Pipeline');
  return { dir, pipeline, enabled: existsSync(join(pipeline, 'Active')) };
}

/**
 * The Obsidian vault folder that mirrors command-center/, so tracker links can
 * open in Obsidian. JOBBOARD_VAULT_DIR names it explicitly; otherwise the
 * documented default (command-center/README.md) is used only when its
 * 03-Pipeline really resolves to this command center. Returns
 * {vault, prefix} or null.
 */
export function detectVault(ccDir, candidate = process.env.JOBBOARD_VAULT_DIR
  || join(homedir(), 'github', 'SDE-Interview-Prep', '16-Interview-Command-Center')) {
  try {
    if (realpathSync(join(candidate, '03-Pipeline')) !== realpathSync(join(ccDir, '03-Pipeline'))) return null;
    for (let d = candidate; d !== dirname(d); d = dirname(d)) {
      if (existsSync(join(d, '.obsidian'))) return { vault: basename(d), prefix: relative(d, candidate).split(sep).join('/') };
    }
  } catch { /* no vault here */ }
  return null;
}

export function obsidianUrl(vaultInfo, relFromCommandCenter) {
  if (!vaultInfo) return null;
  const file = [vaultInfo.prefix, relFromCommandCenter].filter(Boolean).join('/');
  return `obsidian://open?vault=${encodeURIComponent(vaultInfo.vault)}&file=${encodeURIComponent(file)}`;
}

function walkMarkdown(dir) {
  if (!existsSync(dir)) return [];
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    const st = statSync(p);
    // A checkout parked under 03-Pipeline/ holds someone else's notes, not trackers (#3762).
    if (st.isDirectory()) { if (!isNestedCheckout(p)) out.push(...walkMarkdown(p)); }
    else if (name.endsWith('.md')) out.push(p);
  }
  return out;
}

// ── Company matching ───────────────────────────────────────────────────────

const LEGAL_SUFFIX_RE = /\b(capital|management|group|llc|l\.?p\.?|inc|ltd|co|company|technologies|technology|trading|securities|partners|investments|asset|advisors|holdings|the)\b/g;

const exactKey = (name) => String(name || '').toLowerCase().replace(/[^a-z0-9]/g, '');

export function companyKey(name) {
  const lower = String(name || '').toLowerCase().replace(/&/g, ' and ');
  const stripped = lower.replace(LEGAL_SUFFIX_RE, ' ').replace(/[^a-z0-9]/g, '');
  return stripped || lower.replace(/[^a-z0-9]/g, '');
}

/**
 * Registry names, ids and WSQ aliases, normalized two ways: `exact` (lowercase
 * alphanumerics) and `stripped` (legal suffixes removed too). A stripped key
 * shared by two registry ids (Citadel / Citadel Securities) is `ambiguous` and
 * resolves to neither.
 */
export function companyIndex(registry) {
  const exact = new Map();
  const stripped = new Map();
  const ambiguous = new Set();
  for (const c of registry) {
    for (const n of [c.name, c.id, ...(c.wsq || [])]) {
      const e = exactKey(n);
      if (e && !exact.has(e)) exact.set(e, c.id);
      const k = companyKey(n);
      if (!k || ambiguous.has(k)) continue;
      if (stripped.has(k) && stripped.get(k) !== c.id) { stripped.delete(k); ambiguous.add(k); } else stripped.set(k, c.id);
    }
  }
  return { exact, stripped, ambiguous };
}

/** Registry id for any of a tracker's names: exact name, then stripped key, then a stripped prefix of 5+ characters either way. */
export function resolveCompanyId(names, index) {
  for (const n of names) if (index.exact.has(exactKey(n))) return index.exact.get(exactKey(n));
  const keys = names.map(companyKey).filter((k) => k && !index.ambiguous.has(k));
  for (const k of keys) if (index.stripped.has(k)) return index.stripped.get(k);
  for (const k of keys) {
    for (const [ik, id] of index.stripped) {
      const [short, long] = k.length <= ik.length ? [k, ik] : [ik, k];
      if (short.length >= 5 && long.startsWith(short)) return id;
    }
  }
  return null;
}

// ── Trackers ───────────────────────────────────────────────────────────────

/**
 * Every tracker note with a company and a stage (the same rule the Python
 * scripts use), with its registry company id when one matches.
 */
export function loadTrackers(cc, registry, vaultInfo = null) {
  if (!cc.enabled) return [];
  const index = companyIndex(registry);
  const out = [];
  for (const folder of ['Active', 'Archive']) {
    for (const path of walkMarkdown(join(cc.pipeline, folder))) {
      const text = readFileSync(path, 'utf-8');
      const fm = readFrontmatter(text);
      if (!fm.company || !('stage' in fm)) continue;
      const names = [fm.company, ...readList(text, 'aliases')];
      const rel = relative(cc.dir, path).split(sep).join('/');
      out.push({
        rel,
        name: basename(path, '.md'),
        company: fm.company,
        companyId: resolveCompanyId(names, index),
        exactKeys: names.map(exactKey).filter(Boolean),
        strippedKeys: names.map(companyKey).filter((k) => k && !index.ambiguous.has(k)),
        role: fm.role || '',
        stage: fm.stage || '',
        status: stageToStatus(fm.stage),
        applied: fm.applied || '',
        nextAction: fm.next_action || '',
        nextActionDate: fm.next_action_date || '',
        resume: fm.resume || '',
        links: readList(text, 'links').filter((l) => /^https?:\/\//i.test(l)),
        archived: folder === 'Archive',
        obsidian: obsidianUrl(vaultInfo, rel),
      });
    }
  }
  return out;
}

/**
 * Whether a tracker is for `job`'s company: the same registry id, or the same
 * company name or alias (exact, or suffix-stripped unless that key is shared by
 * two registry firms), so trackers for firms outside the registry still count.
 */
export function sameCompany(t, job) {
  if (t.companyId && t.companyId === job.companyId) return true;
  const e = exactKey(job.companyName);
  const k = companyKey(job.companyName);
  return Boolean((e && t.exactKeys.includes(e)) || (k && t.strippedKeys.includes(k)));
}

/** The non-archived trackers an application on `job` could already be. */
export function candidateTrackers(trackers, job) {
  return trackers.filter((t) => !t.archived && sameCompany(t, job));
}

/**
 * The tracker a board-side link names. Archiving moves a note from Active/ to
 * Archive/ under the same company folder, so the path below that folder is
 * matched when the exact rel is gone.
 */
export function findTracker(trackers, rel) {
  const below = (r) => String(r).split('/').slice(2).join('/');
  return trackers.find((t) => t.rel === rel) || (below(rel) && trackers.find((t) => below(t.rel) === below(rel))) || null;
}

/**
 * Link trackers to board jobs by posting URL. `keyFor(companyId, url)` is the
 * board's jobKey, so a firm-domain ?gh_jid= link and a job-boards.greenhouse.io
 * link to the same requisition land on the same job. A tracker whose company
 * is unknown can still link through an exact job URL. `boardLinks` (job id ->
 * tracker rel, kept in the board's state) link a posting to a tracker without
 * editing the note, and count exactly like a URL link.
 * @returns {Map<string, object>} job id -> tracker (the most recently applied wins)
 */
export function linkTrackersToJobs(trackers, jobs, keyFor, boardLinks = {}) {
  const jobIds = new Set(jobs.map((j) => j.id));
  const byUrl = new Map();
  for (const j of jobs) for (const u of [j.url, ...Object.values(j.sources || {}).map((s) => s.url)]) if (u) byUrl.set(u, j.id);
  const linked = new Map();
  const link = (id, t) => {
    const prev = linked.get(id);
    if (!prev || String(t.applied) > String(prev.applied)) linked.set(id, t);
    t.jobId = id;
  };
  for (const t of trackers) {
    for (const url of t.links) {
      const id = (t.companyId && jobIds.has(keyFor(t.companyId, url)) && keyFor(t.companyId, url)) || byUrl.get(url);
      if (id) link(id, t);
    }
  }
  for (const [id, rel] of Object.entries(boardLinks)) {
    const t = jobIds.has(id) && findTracker(trackers, rel);
    if (t) link(id, t);
  }
  return linked;
}

// ── Creating a tracker ─────────────────────────────────────────────────────

const TRACK_FOR_CATEGORY = {
  'Quant Dev': 'quant-dev',
  'Quant Research': 'quant-research',
  Trading: 'quant-research',
  'AI/ML': 'ai-eng',
  'Software Eng': 'sde',
  Data: 'sde',
  Risk: 'quant-research',
};

export function slugify(s, max = 60) {
  return String(s || '').normalize('NFKD').replace(/[^\w\s-]/g, ' ').trim().split(/[\s_-]+/).filter(Boolean)
    .map((w) => w[0].toUpperCase() + w.slice(1)).join('-').slice(0, max).replace(/-+$/, '');
}

// Double-quoted YAML scalar that needs no escapes: the line-based readers
// (here and tracker_frontmatter.py) strip the outer quotes but do not unescape,
// so a quote or backslash inside would read differently in Obsidian's YAML.
const q = (s) => `"${String(s ?? '').replace(/["\\]/g, "'").replace(/[\r\n]+/g, ' ').trim()}"`;

function addDays(isoDate, n) {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

const TERMINAL_STAGES = new Set(['offer', 'rejected']);

/**
 * The tracker note for a job you just applied to (schema:
 * 03-Pipeline/_Application-Schema.md). `applied` is the date you applied
 * (default today); a terminal stage gets no follow-up next action.
 */
export function renderTrackerNote(job, { today, applied = today, resume = '', source = 'Job board', stage = 'applied' }) {
  const followUp = !TERMINAL_STAGES.has(stage);
  const tracks = [...new Set([TRACK_FOR_CATEGORY[job.category] || 'sde', ...((job.tags || []).includes('Low Latency') ? ['low-latency'] : [])])];
  const lines = [
    '---',
    `company: ${q(job.companyName)}`,
    'aliases: []',
    `role: ${q(job.title)}`,
    `stage: ${stage}`,
    `status: ${q(stage === 'applied' ? 'Applied via the job board' : `Marked ${stage} on the job board`)}`,
    `track: [${tracks.join(', ')}]`,
    `level: ${q(job.seniority || '')}`,
    `source: ${q(source)}`,
    'referrer:',
    `applied: ${applied}`,
    followUp ? `next_action: ${q('Follow up if no reply')}` : 'next_action:',
    followUp ? `next_action_date: ${addDays(today, 14)}` : 'next_action_date:',
    'priority: medium',
    'confidence: 3',
    `comp_band: ${q(job.salary || '')}`,
    `location: ${q(job.location || (job.regions || [job.region]).filter(Boolean).join(' / '))}`,
    `resume: ${q(resume)}`,
    `jobboard_id: ${q(job.id)}`,
    `links: [${q(job.url)}]`,
    'tags: [interview-tracker, active-pipeline]',
    '---',
    '',
    `# ${job.companyName} - ${job.title}`,
    '',
    `Created by the job board on ${today}. Update \`stage\` here as the process moves; the board and the daily sync read it.`,
    '',
    '## Notes',
    '',
    '## Timeline',
    '',
    `- ${today} ${stage}: ${stage === 'applied' ? 'Applied' : `Marked ${stage}`} via the job board${resume ? ` (resume ${resume})` : ''}`,
    '',
  ];
  return lines.join('\n');
}

/**
 * Write a tracker for `job` under Active/<company folder>/, reusing the folder
 * an existing tracker for the same company already uses. Never overwrites: a
 * name collision gets a -2, -3, ... suffix, and an existing tracker already
 * linked to the job is returned instead of writing anything.
 * @returns {{created: boolean, rel: string}}
 */
export function createTrackerForJob(cc, job, { trackers, linked, today, applied = today, resume = '', source, stage = 'applied' }) {
  if (!cc.enabled) throw new Error('command center not found (expected command-center/03-Pipeline/Active)');
  const existing = linked.get(job.id);
  if (existing) return { created: false, rel: existing.rel };
  const sibling = trackers.find((t) => sameCompany(t, job));
  const folder = sibling ? sibling.rel.split('/')[2] : slugify(job.companyName, 40);
  const dir = join(cc.pipeline, 'Active', folder);
  mkdirSync(dir, { recursive: true });
  const stem = `${slugify(job.companyName, 40)}-${slugify(job.title)}-Tracker`;
  const text = renderTrackerNote(job, { today, applied, resume, source, stage });
  for (let n = 1; n < 100; n++) {
    const path = join(dir, `${stem}${n === 1 ? '' : `-${n}`}.md`);
    try {
      writeFileSync(path, text, { encoding: 'utf-8', flag: 'wx' });
      return { created: true, rel: relative(cc.dir, path).split(sep).join('/') };
    } catch (err) {
      if (err.code !== 'EEXIST') throw err;
    }
  }
  throw new Error(`could not find a free tracker file name for ${stem}`);
}

// ── Resumes and reports ────────────────────────────────────────────────────

/** resume/<track>/<length>/*.pdf -> [{variant: 'quant/one-page', path}] */
export function discoverResumes(root) {
  const base = join(root, 'resume');
  if (!existsSync(base)) return [];
  const out = [];
  for (const track of readdirSync(base).sort()) {
    const trackDir = join(base, track);
    if (track.startsWith('.') || track.trim() !== track || !statSync(trackDir).isDirectory()) continue;
    for (const length of readdirSync(trackDir).sort()) {
      const dir = join(trackDir, length);
      if (length.startsWith('.') || !statSync(dir).isDirectory()) continue;
      const pdf = readdirSync(dir).find((f) => f.toLowerCase().endsWith('.pdf') && !f.startsWith('~$'));
      if (pdf) out.push({ variant: `${track}/${length}`, path: join(dir, pdf) });
    }
  }
  return out;
}

/** career-ops evaluation reports: [{num, file, url, score}] from their header lines. */
export function loadReports(root) {
  const dir = join(root, 'reports');
  if (!existsSync(dir)) return [];
  const out = [];
  for (const file of readdirSync(dir).sort()) {
    const m = file.match(/^(\d{3,})-.*\.md$/);
    if (!m) continue;
    const head = readFileSync(join(dir, file), 'utf-8').split('\n').slice(0, 40).join('\n');
    const url = head.match(/^\*\*URL:\*\*\s*(\S+)/m)?.[1];
    if (!url || !/^https?:\/\//i.test(url)) continue;
    out.push({ num: m[1], file, url, score: head.match(/^\*\*Score:\*\*\s*([\d.]+\/5)/m)?.[1] || '' });
  }
  return out;
}

// ── Obsidian note ──────────────────────────────────────────────────────────

const cell = (s) => String(s ?? '').replace(/\|/g, '/').replace(/\n/g, ' ');

/**
 * 03-Pipeline/_Job-Board.md: the board as seen from the command center.
 * `focus` is the list of focus roles (USA, QD/QR/AI/SWE, experienced, not applied).
 */
export function renderJobBoardNote({ today, jobs, companies, trackers, linked, focus, port = 4178 }) {
  const open = jobs.filter((j) => j.active);
  const tracked = [...linked.entries()].map(([id, t]) => ({ t, j: jobs.find((x) => x.id === id) })).filter((x) => x.j);
  const trackerCompanies = companies.filter((c) => trackers.some((t) => t.companyId === c.id));
  const lines = [
    '---', 'type: dashboard', 'status: generated', '---', '',
    '# Job board', '',
    `Generated by \`jobboard.mjs\` on ${today}; it is overwritten on every refresh.`,
    `Full board: http://127.0.0.1:${port}/ (\`node jobboard/jobboard.mjs serve --open\`).`, '',
    `Open roles: ${open.length} at ${companies.filter((c) => c.open).length} companies; ${open.filter((j) => j.status === 'Not Applied').length} not applied.`,
    `Trackers: ${trackers.length} (${trackers.filter((t) => !t.archived).length} active), ${tracked.length} linked to a board posting.`, '',
    '## Your applications on the board', '',
  ];
  if (tracked.length) {
    lines.push('| Company | Role | Stage | Tracker | Posting |', '| :--- | :--- | :--- | :--- | :--- |');
    for (const { t, j } of tracked) lines.push(`| ${cell(j.companyName)} | ${cell(j.title)} | ${cell(t.stage)} | [[${t.name}]] | [posting](${j.url}) |`);
  } else lines.push('None yet: confirm an application on the board and it creates the tracker.');
  lines.push('', '## Companies you track', '');
  if (trackerCompanies.length) {
    lines.push('| Company | Your trackers | Open roles | Not applied | Careers |', '| :--- | :--- | ---: | ---: | :--- |');
    for (const c of trackerCompanies) {
      const ts = trackers.filter((t) => t.companyId === c.id).map((t) => `[[${t.name}]] (${t.stage})`).join(', ');
      lines.push(`| ${cell(c.name)} | ${ts} | ${c.open} | ${c.notApplied} | ${c.website ? `[careers](${c.website})` : ''} |`);
    }
  } else lines.push('None.');
  lines.push('', `## Focus roles not applied (${focus.length > 60 ? 'newest 60 of ' : ''}${focus.length})`, '',
    'USA, Quant Dev / Quant Research / AI-ML / Software Eng, excluding intern and new-grad roles.', '');
  if (focus.length) {
    lines.push('| Posted | Company | Role | Location |', '| :--- | :--- | :--- | :--- |');
    for (const j of focus.slice(0, 60)) lines.push(`| ${(j.postedAt || '').slice(0, 10)} | ${cell(j.companyName)} | [${cell(j.title)}](${j.url}) | ${cell(j.location)} |`);
  } else lines.push('None.');
  return lines.join('\n') + '\n';
}
