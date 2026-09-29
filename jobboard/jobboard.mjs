#!/usr/bin/env node
/**
 * jobboard.mjs - Quant / trading / AI job board with application tracking
 *
 * FORK-LOCAL. The whole jobboard/ directory is declared in config/local-paths.txt
 * so `update-system.mjs apply` never overwrites or prunes it.
 *
 * SOURCES (zero LLM tokens, public endpoints only)
 *   wsq    thewallstreetquants.com/openings - a Next.js page whose server payload
 *          embeds every listing as JSON (title, firm, firm type, city, role, xp,
 *          salary, apply URL). Parsed from the RSC stream, no browser needed.
 *   ats    each company's public ATS board listed in jobboard/companies.yml,
 *          fetched through the same providers/ modules scan.mjs uses.
 *
 * MERGE. A job's id is `{companyId}:{externalId}`, where externalId is the ATS
 * requisition id pulled from the URL (Greenhouse gh_jid or /jobs/N, Lever/Ashby
 * UUID, Workday _R123, Eightfold/Oracle /job/N). WSQ links a firm's own careers
 * domain with ?gh_jid=N and the ATS scan links job-boards.greenhouse.io/.../jobs/N,
 * so both collapse onto one job. Every job records which sources list it; a
 * source that fetched SUCCESSFULLY and no longer lists the job marks it gone,
 * and a job with no live source left is closed. A failed fetch never closes
 * anything (a timeout is not evidence a role closed).
 *
 * DATA (user layer, gitignored)
 *   data/jobboard/jobs.json      merged job store, rewritten by refresh/ingest/scan
 *   data/jobboard/state.json     YOUR application state per job + manual jobs;
 *                                written by `serve` and `mark`. ingest-wsq/refresh
 *                                only re-key entries when a previously unmapped
 *                                WSQ firm is added to companies.yml
 *   data/jobboard/runs.tsv       one line per source run (for "last refreshed")
 *   data/jobboard/companies.md   the company directory, regenerated on refresh
 *
 * USAGE
 *   node jobboard/jobboard.mjs                      summary (counts, last refresh, next steps)
 *   node jobboard/jobboard.mjs refresh              ingest WSQ + scan every company board
 *   node jobboard/jobboard.mjs ingest-wsq           WSQ only
 *   node jobboard/jobboard.mjs scan [--company id]  company boards only
 *   node jobboard/jobboard.mjs serve [--port 4178] [--open]   the web app (127.0.0.1 only)
 *   node jobboard/jobboard.mjs list [--status S] [--category C] [--company id]
 *                                   [--type T] [--region R] [--q text] [--limit N] [--full]
 *   node jobboard/jobboard.mjs mark <jobId> <status> [--note text]
 *   node jobboard/jobboard.mjs companies
 *   node jobboard/jobboard.mjs --self-test
 */

import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync, appendFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as yaml from 'js-yaml';

import { getCareerOpsRoot } from '../path-resolver.mjs';
import { BROWSER_LIKE_USER_AGENT } from '../user-agent.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..');
const REGISTRY_PATH = join(HERE, 'companies.yml');
const UI_PATH = join(HERE, 'ui.html');

const WSQ_URL = 'https://www.thewallstreetquants.com/openings';
const DEFAULT_PORT = 4178;
const BOARD_TIMEOUT_MS = 180_000;
const SCAN_CONCURRENCY = 6;

export const STATUSES = ['Not Applied', 'Saved', 'Applied', 'Interviewing', 'Offer', 'Rejected', 'Not Interested'];
export const CATEGORIES = ['Quant Research', 'Quant Dev', 'AI/ML', 'Software Eng', 'Data', 'Trading', 'Risk'];
export const SENIORITIES = ['Intern', 'New Grad', 'Entry', 'Mid-Senior', 'Senior+'];
const NOTES_MAX = 4000;

function dataPaths() {
  const dir = join(getCareerOpsRoot(), 'data', 'jobboard');
  return {
    dir,
    jobs: join(dir, 'jobs.json'),
    state: join(dir, 'state.json'),
    runs: join(dir, 'runs.tsv'),
    companiesMd: join(dir, 'companies.md'),
  };
}

// ── IO helpers ────────────────────────────────────────────────────────────

function readJson(path, fallback) {
  if (!existsSync(path)) return fallback;
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const tmp = `${path}.${process.pid}.tmp`;
  writeFileSync(tmp, JSON.stringify(value, null, 1) + '\n', 'utf-8');
  renameSync(tmp, path);
}

export function loadRegistry(path = REGISTRY_PATH) {
  const doc = yaml.load(readFileSync(path, 'utf-8'));
  const list = doc?.companies;
  if (!Array.isArray(list)) throw new Error(`${path}: expected a top-level "companies" list`);
  const seen = new Set();
  return list.map((c, i) => {
    if (!c?.id || !c?.name || !c?.type) throw new Error(`${path}: entry ${i} needs id, name and type`);
    if (seen.has(c.id)) throw new Error(`${path}: duplicate id "${c.id}"`);
    seen.add(c.id);
    return {
      id: String(c.id),
      name: String(c.name),
      type: String(c.type),
      wsq: (c.wsq || []).map(String),
      boards: (c.boards || []).map(String),
      website: c.website ? String(c.website) : '',
      filter: c.filter === 'strict' ? 'strict' : 'all',
    };
  });
}

function emptyStore() {
  return { version: 1, updatedAt: null, jobs: {}, companyRuns: {} };
}

function emptyState() {
  return { version: 1, jobs: {}, manual: [] };
}

// ── Classification (pure) ─────────────────────────────────────────────────

// Roles that are never engineering/quant work, even when the title names a
// quant team ("Lead Technical Recruiter (Quant Engineering)").
const HARD_EXCLUDE_RE = /recruit|talent acquisition|sourcer\b|counsel|attorney|paralegal|receptionist|executive assistant|\bchef\b|culinary|payroll|compensation|financial planning/i;

// Non-engineering roles; an engineering noun in the title overrides these.
const EXCLUDE_RE = new RegExp([
  'human resources', '\\bhr\\b', 'people partner', 'benefits', 'legal', 'accountant', 'accounting',
  '\\btax\\b', 'administrative', 'office manager', 'facilities', 'workplace', 'marketing',
  'communications', 'brand', 'business development', 'investor relations', 'client service',
  'relationship manager', 'wealth', 'advisor', '\\bevents?\\b', 'hospitality', 'procurement', 'kyc',
  'customer support', 'customer success', 'support specialist', 'content', 'governance', 'policy',
  'fraud investigat', 'collections', 'underwrit', 'branch', 'teller', 'mortgage', 'loan officer',
  'nurse', 'driver', 'warehouse', 'product manager', 'product owner', 'program manager',
  'project manager', 'scrum master', 'business analyst', 'pmo', 'enablement', 'adoption',
  'transformation', 'consultant', 'compliance', 'sourcing', 'surveillance', 'product strategy',
].join('|'), 'i');
const ENGINEERING_NOUN_RE = /engineer\b|engineering\b|developer|programmer|scientist|researcher|quant|architect|\bsre\b|devops|technolog/i;

// Engineers who do not write software.
const NON_SOFTWARE_ENGINEER_RE = /\b(sales|solutions?|field|facilities|electrical|mechanical|civil|hvac|audio|video|desktop support|help ?desk|it support|end user|site engineer|building)\b/i;

const AI_RE = /\b(machine learning|ml|ai|artificial intelligence|deep learning|llms?|genai|gen ai|generative|nlp|computer vision|applied scientist|mlops|inference|reinforcement learning|agentic)\b/i;
// "AI" in a strategy/PMO/product title is not an AI engineering role.
const AI_NOUN_RE = /engineer|developer|scientist|research|architect|programmer|modell?er|mlops|machine learning|\bml\b|deep learning|\bnlp\b/i;
const QUANT_WORD_RE = /\bquant|alpha\b|\bsignals?\b|systematic|statistic|\bqr\b/i;
// Explicit quant-developer titles win even inside "Quantitative Trading & Research - ... Quantitative Developer".
const QD_STRONG_RE = /quant(itative)?[\s-]*(dev|developer|engineer|software|technolog|programmer)|\bstrats?\b[^,]*(engineer|developer)|front office quant/i;
const QR_RE = /research|analyst|strateg|modell?er|scientist|\btrader\b|\bqr\b|\balpha\b|\bsignals?\b|systematic (trading|equit|invest|macro|credit)/i;
// Low-latency / trading-infrastructure signals; they make a title Quant Dev only
// alongside an engineering noun or a hard systems keyword.
const QD_WEAK_RE = /low[\s-]?latency|market[\s-]?data|trading (system|software|infra|technolog|platform|engineer|developer|application|connectivity)|\bexecution\b|\balgo(rithmic)?\b|\bhft\b|\bfpga\b|electronic trading|core (dev|eng)|c\+\+|\bkdb\b|pricing (library|engineer|developer)|order (management|routing)|exchange (connectivity|core)|matching engine|\boms\b/i;
const QD_HARD_RE = /c\+\+|\bfpga\b|\bhft\b|\bkdb\b|low[\s-]?latency/i;
const TRADING_RE = /\btrader\b|trading (analyst|associate|intern|assistant|desk)|market maker|portfolio manager|\bpm\b/i;
const RISK_RE = /\brisk\b/i;
const DATA_RE = /\bdata (engineer|scientist|analyst|platform|infrastructure|science)|analytics engineer|\bdata\b/i;
const SWE_RE = /software|developer|engineer|programmer|\bsre\b|site reliability|devops|infrastructure|platform|back[\s-]?end|full[\s-]?stack|front[\s-]?end|\bsystems?\b|python|\brust\b|\bjava\b|golang|kernel|network|architect|technolog|\bswe\b|\bsde\b/i;
// A title at a large bank/fintech has to carry one of these to count (filter: strict).
const STRICT_SIGNAL_RE = /quant|c\+\+|python|low[\s-]?latency|trading|machine learning|\bml\b|\bai\b|llm|algorithm|\balgo\b|market[\s-]?data|electronic|execution|\bstrats?\b|\bkdb\b|\brust\b|\bhft\b|fpga|derivative|pricing|data scien|research|systematic|options|fixed income|\bfx\b|equities|crypto|blockchain|matching engine|exchange/i;

const WSQ_ROLE_FALLBACK = { Dev: 'Software Eng', Quant: 'Quant Research', ML: 'AI/ML', Data: 'Data', Risk: 'Risk', Strat: 'Quant Research' };

/**
 * Category for a title, or null when the posting is not a tech/quant role.
 * @param {string} title
 * @param {{wsqRole?: string, strict?: boolean}} [opts]  wsqRole: WSQ's own
 *   label, used as the fallback because WSQ already curates its listings.
 */
export function classifyCategory(title, { wsqRole, strict = false } = {}) {
  const t = String(title || '');
  const fallback = wsqRole ? WSQ_ROLE_FALLBACK[wsqRole] ?? null : null;
  if (HARD_EXCLUDE_RE.test(t)) return fallback;
  if (EXCLUDE_RE.test(t) && !ENGINEERING_NOUN_RE.test(t)) return fallback;
  if (strict && !STRICT_SIGNAL_RE.test(t)) return fallback;
  const trader = /\btrader\b/i.test(t);
  if (QD_STRONG_RE.test(t)) return 'Quant Dev';
  if (QUANT_WORD_RE.test(t) && QR_RE.test(t)) return trader ? 'Trading' : 'Quant Research';
  if (AI_RE.test(t) && AI_NOUN_RE.test(t)) return 'AI/ML';
  if (/research scientist|\bresearcher\b/i.test(t)) return 'Quant Research';
  if (QD_WEAK_RE.test(t) && (ENGINEERING_NOUN_RE.test(t) || QD_HARD_RE.test(t))) return 'Quant Dev';
  if (TRADING_RE.test(t)) return 'Trading';
  if (RISK_RE.test(t)) return 'Risk';
  if (DATA_RE.test(t) && !/engineer/i.test(t.replace(/data engineer/i, ''))) return 'Data';
  if (SWE_RE.test(t) && !NON_SOFTWARE_ENGINEER_RE.test(t)) return 'Software Eng';
  if (/\btrading\b/i.test(t)) return 'Trading';
  return fallback;
}

const WSQ_XP = { Intern: 'Intern', 'New Grad': 'New Grad', 'Entry Lvl': 'Entry', 'Mid-Senior': 'Mid-Senior', Discovery: 'Entry' };

export function classifySeniority(title, wsqXp) {
  const t = String(title || '');
  if (/\bintern(ship)?s?\b|summer (analyst|associate)|co-?op\b|placement/i.test(t)) return 'Intern';
  if (/graduate|new grad|campus|university|\b20\d\d start\b|\(20\d\d start\)|early career/i.test(t)) return 'New Grad';
  if (/\b(senior|sr\.?|lead|principal|staff|head|director|\bvp\b|vice president|managing director|manager|chief|architect)\b/i.test(t)) return 'Senior+';
  if (/\b(junior|jr\.?|entry|associate|analyst i\b|engineer i\b)\b/i.test(t)) return 'Entry';
  if (wsqXp && WSQ_XP[wsqXp]) return WSQ_XP[wsqXp];
  return 'Mid-Senior';
}

const REGION_TABLE = [
  ['Remote', /\bremote\b/i],
  ['India', /india|mumbai|bangalore|bengaluru|gurgaon|gurugram|hyderabad|chennai|pune|delhi|noida|gift city|kolkata/i],
  ['Asia-Pacific', /singapore|hong kong|sydney|melbourne|tokyo|shanghai|beijing|shenzhen|seoul|taipei|hanoi|ho chi minh|manila|kuala lumpur|australia|japan|china|korea|taiwan|vietnam|philippines|malaysia|\bapac\b/i],
  ['Middle East', /dubai|abu dhabi|tel aviv|ramat gan|israel|riyadh|doha|bahrain|\buae\b|herzliya/i],
  ['Europe', /london|amsterdam|dublin|paris|frankfurt|zurich|geneva|milan|madrid|barcelona|budapest|warsaw|krakow|prague|berlin|munich|hamburg|aarhus|copenhagen|stockholm|oslo|helsinki|kajaani|lisbon|belfast|bristol|edinburgh|glasgow|cork|luxembourg|brussels|vienna|sofia|bucharest|cluj|limassol|cyprus|malta|gibraltar|jersey\b(?! city)|guernsey|\buk\b|united kingdom|england|ireland|netherlands|france|germany|switzerland|spain|italy|poland|hungary|romania|bulgaria|europe|\bemea\b/i],
  ['Canada', /toronto|montreal|vancouver|calgary|ottawa|canada|quebec/i],
  ['Latin America', /s[aã]o paulo|montevideo|mexico city|buenos aires|bogot|santiago|brazil|uruguay|argentina|colombia|chile/i],
  ['USA', /new york|\bnyc\b|chicago|boston|san francisco|seattle|austin|houston|dallas|miami|denver|boulder|philadelphia|bala cynwyd|stamford|greenwich|norwalk|jersey city|new jersey|berkeley|palo alto|mountain view|menlo park|los angeles|san jose|atlanta|charlotte|richmond|plano|columbus|minneapolis|salt lake|pittsburgh|nashville|washington|wilmington|tampa|phoenix|portland|raleigh|kansas city|st\.? louis|detroit|east setauket|radnor|red bank|princeton|westport|connecticut|florida|texas|california|illinois|massachusetts|pennsylvania|united states|\busa\b|\bus\b|\b(ny|il|ca|tx|fl|ct|nj|wa|pa|ga|nc|va|mn|oh|ut|az|dc|mo|mi|tn)\b/i],
];

// WSQ's 'North America' and 'Global' span several regions (Montreal, Sao Paulo),
// so those listings are placed by their cities instead.
const WSQ_BROAD_REGIONS = new Set(['North America', 'Global']);

const LOCATION_SEPARATOR_RE = /\s*[;/|·]\s*|\s+or\s+/i;

function matchRegion(location) {
  for (const [region, re] of REGION_TABLE) if (re.test(location)) return region;
  return null;
}

/**
 * Every region a posting's locations map to, primary first.
 * @param {string|string[]} locations WSQ's city list, or a location string
 *   split on ; / | · and "or"; each part is classified on its own.
 * @param {string} [wsqRegion] WSQ's own region, which leads unless it is broad.
 */
export function classifyRegions(locations, wsqRegion) {
  const parts = (Array.isArray(locations) ? locations : String(locations || '').split(LOCATION_SEPARATOR_RE))
    .map((p) => String(p).trim())
    .filter(Boolean);
  const found = [wsqRegion && !WSQ_BROAD_REGIONS.has(wsqRegion) ? wsqRegion : null, ...parts.map(matchRegion)].filter(Boolean);
  if (found.length) return [...new Set(found)];
  const loc = parts.join(' ');
  if (!loc) return ['Unknown'];
  return [/\d+\s+locations/i.test(loc) ? 'Multiple' : 'Other'];
}

const TECH_TAGS = [
  ['C++', /c\+\+|\bcpp\b/i],
  ['Python', /\bpython\b/i],
  ['Rust', /\brust\b/i],
  ['OCaml', /\bocaml\b/i],
  ['Java', /\bjava\b(?!script)/i],
  ['C#', /\bc#|\.net\b/i],
  ['Go', /\bgolang\b|\bgo developer\b/i],
  ['KDB/q', /\bkdb\b|\bq\/kdb/i],
  ['FPGA', /\bfpga\b|verilog|\bvhdl\b/i],
  ['Low Latency', /low[\s-]?latency|ultra[\s-]?low|kernel bypass/i],
  ['ML', /machine learning|\bml\b|deep learning|pytorch|tensorflow/i],
  ['LLM', /\bllms?\b|genai|generative ai|large language/i],
];

export function techTags(...texts) {
  const text = texts.filter(Boolean).join('\n');
  return TECH_TAGS.filter(([, re]) => re.test(text)).map(([tag]) => tag);
}

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

/** ATS requisition id carried by a posting URL, or null. */
export function externalId(url) {
  let u;
  try { u = new URL(url); } catch { return null; }
  const gh = u.searchParams.get('gh_jid');
  if (gh && /^\d+$/.test(gh)) return `gh-${gh}`;
  const host = u.hostname.toLowerCase();
  const path = u.pathname;
  if (host.endsWith('greenhouse.io')) {
    const m = path.match(/\/jobs\/(\d+)/);
    if (m) return `gh-${m[1]}`;
  }
  if (host === 'jobs.lever.co' || host === 'jobs.ashbyhq.com') {
    const m = path.match(UUID_RE);
    if (m) return `uuid-${m[0].toLowerCase()}`;
  }
  if (host.endsWith('myworkdayjobs.com') || host.endsWith('myworkdaysite.com')) {
    const m = path.match(/_((?:[A-Z]{1,4}-?)?\d{3,})(?:-\d+)?\/?$/);
    if (m) return `wd-${m[1]}`;
  }
  if (host.endsWith('eightfold.ai') || host.endsWith('oraclecloud.com')) {
    const m = path.match(/\/job\/(\d+)/);
    if (m) return `job-${m[1]}`;
  }
  // Firm-hosted pages that embed a Greenhouse id in the path.
  let m = path.match(/\/(?:position|jobs|job)\/(\d{6,})\/?$/);
  if (m) return `gh-${m[1]}`;
  m = path.match(/\/job\/(\d{6,})\/?/);
  if (m) return `gh-${m[1]}`;
  return null;
}

function normalizedUrl(url) {
  try {
    const u = new URL(url);
    u.hash = '';
    for (const k of [...u.searchParams.keys()]) if (/^(utm_|lang$|source$|ref$|gh_src$)/i.test(k)) u.searchParams.delete(k);
    return `${u.hostname.toLowerCase().replace(/^www\./, '')}${u.pathname.replace(/\/$/, '')}${u.search}`;
  } catch {
    return String(url).trim().toLowerCase();
  }
}

export function isHttpUrl(url) {
  try {
    const { protocol } = new URL(url);
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
  }
}

export function jobKey(companyId, url) {
  return `${companyId}:${externalId(url) ?? normalizedUrl(url)}`;
}

function formatSalary(s) {
  if (!s) return '';
  if (typeof s === 'string') return s.replace(/\$\$/g, '$').trim();
  const fmt = (n) => (typeof n === 'number' ? n.toLocaleString('en-US') : '');
  const cur = s.currency && s.currency !== 'USD' ? `${s.currency} ` : '$';
  if (s.min && s.max) return `${cur}${fmt(s.min)} - ${cur}${fmt(s.max)}`;
  if (s.min || s.max) return `${cur}${fmt(s.min || s.max)}`;
  return '';
}

function isoOrNull(v) {
  if (v === undefined || v === null || v === '') return null;
  const d = typeof v === 'number' ? new Date(v) : new Date(String(v));
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

// ── WSQ parsing ───────────────────────────────────────────────────────────

/** Decode the JSON array that starts at text[start] (which must be '['). */
function sliceJsonArray(text, start) {
  let depth = 0;
  let inString = false;
  for (let i = start; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (ch === '\\') i++;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === '[' || ch === '{') depth++;
    else if (ch === ']' || ch === '}') {
      depth--;
      if (depth === 0) return JSON.parse(text.slice(start, i + 1));
    }
  }
  throw new Error('unterminated JSON array');
}

/** Listings embedded in the openings page's Next.js RSC stream. */
export function parseWsqHtml(html) {
  let payload = '';
  const pushRe = /self\.__next_f\.push\((\[[\s\S]*?\])\)<\/script>/g;
  for (const m of html.matchAll(pushRe)) {
    try {
      const arr = JSON.parse(m[1]);
      if (typeof arr[1] === 'string') payload += arr[1];
    } catch { /* non-string chunk (bootstrap markers) */ }
  }
  const at = payload.indexOf('"jobs":[');
  if (at < 0) throw new Error('WSQ page: no "jobs" array in the server payload - the page layout changed');
  const jobs = sliceJsonArray(payload, at + '"jobs":'.length);
  if (!Array.isArray(jobs) || jobs.length === 0) throw new Error('WSQ page: "jobs" array is empty');
  const bad = jobs.filter((j) => !j?.title || !j?.firm || !j?.url);
  if (bad.length > jobs.length * 0.05) throw new Error(`WSQ page: ${bad.length}/${jobs.length} listings lack title/firm/url`);
  return jobs.filter((j) => j?.title && j?.firm && j?.url);
}

async function fetchWsq() {
  const res = await fetch(WSQ_URL, {
    headers: { 'user-agent': BROWSER_LIKE_USER_AGENT, accept: 'text/html' },
    signal: AbortSignal.timeout(60_000),
  });
  if (!res.ok) throw new Error(`WSQ fetch: HTTP ${res.status}`);
  return parseWsqHtml(await res.text());
}

// ── Merge ─────────────────────────────────────────────────────────────────

const VAGUE_REGIONS = new Set(['Multiple', 'Unknown', 'Other']);

/**
 * Fold one successful source run into the store.
 * @param {object} store
 * @param {string} sourceKey   'wsq' or 'ats:<board url>'
 * @param {Array<object>} incoming normalized jobs ({id, ...fields, url})
 * @param {string} now ISO timestamp
 * @param {(job: object) => boolean} [scope] which existing jobs this source is
 *   authoritative for; jobs in scope that it no longer lists are marked gone.
 */
export function applySourceRun(store, sourceKey, incoming, now, scope = () => true) {
  const seen = new Set();
  let added = 0;
  for (const job of incoming) {
    seen.add(job.id);
    const prev = store.jobs[job.id];
    const sources = { ...(prev?.sources || {}), [sourceKey]: { url: job.url, seenAt: now, gone: false } };
    if (!prev) added++;
    // ATS data wins over WSQ for fields both carry (it is the firm's own board),
    // but never erase a field the other source filled.
    const atsLive = Object.entries(prev?.sources || {}).some(([k, src]) => k.startsWith('ats:') && !src.gone);
    const preferIncoming = sourceKey !== 'wsq' || !atsLive;
    const merged = { ...(preferIncoming ? prev : job), ...(preferIncoming ? job : prev) };
    for (const k of ['salary', 'postedAt', 'location', 'wsqRole']) merged[k] = merged[k] || prev?.[k] || job[k] || (k === 'postedAt' ? null : '');
    // "2 Locations" from an ATS says less than WSQ's resolved regions.
    const regions = [...new Set([merged.region, ...(job.regions || [job.region]), ...(prev?.regions || [prev?.region])].filter(Boolean))];
    const specific = regions.filter((r) => !VAGUE_REGIONS.has(r));
    merged.regions = specific.length ? specific : regions.slice(0, 1);
    merged.region = merged.regions[0];
    merged.tags = [...new Set([...(prev?.tags || []), ...(job.tags || [])])];
    merged.sources = sources;
    merged.firstSeen = prev?.firstSeen || now;
    merged.active = true;
    merged.closedAt = null;
    store.jobs[job.id] = merged;
  }
  let gone = 0;
  for (const job of Object.values(store.jobs)) {
    if (seen.has(job.id) || !job.sources?.[sourceKey] || !scope(job)) continue;
    if (!job.sources[sourceKey].gone) {
      job.sources[sourceKey] = { ...job.sources[sourceKey], gone: true };
      const stillLive = Object.values(job.sources).some((s) => !s.gone);
      if (!stillLive && job.active) {
        job.active = false;
        job.closedAt = now;
        gone++;
      }
    }
  }
  store.updatedAt = now;
  return { added, gone, total: incoming.length };
}

function wsqFallbackId(firm) {
  return `wsq-${String(firm).toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
}

/**
 * Re-key jobs filed under a WSQ fallback company id (`wsq-<slug>`) once that
 * firm is mapped in companies.yml, so tracked state follows the posting.
 * Existing store records and state under the new id are never overwritten;
 * conflicting old state is left in place rather than dropped.
 * @param {Map<string, {id: string, name: string, type: string}>} renames old companyId -> registry company
 */
export function migrateCompanyIds(store, state, renames) {
  const rekey = (id) => {
    const at = id.indexOf(':');
    const company = at > 0 ? renames.get(id.slice(0, at)) : undefined;
    return company ? { company, id: `${company.id}${id.slice(at)}` } : null;
  };
  let jobs = 0;
  let tracked = 0;
  for (const [oldId, job] of Object.entries(store.jobs)) {
    const next = rekey(oldId);
    if (!next) continue;
    if (!store.jobs[next.id]) store.jobs[next.id] = { ...job, id: next.id, companyId: next.company.id, companyName: next.company.name, firmType: next.company.type };
    delete store.jobs[oldId];
    jobs++;
  }
  for (const [oldId, rec] of Object.entries(state.jobs)) {
    const next = rekey(oldId);
    if (!next || state.jobs[next.id]) continue;
    state.jobs[next.id] = rec;
    delete state.jobs[oldId];
    tracked++;
  }
  return { jobs, tracked };
}

function wsqToJob(raw, companyByWsq) {
  if (!isHttpUrl(raw.url)) return null;
  const company = companyByWsq.get(raw.firm);
  const companyId = company?.id ?? wsqFallbackId(raw.firm);
  const cities = Array.isArray(raw.cities) && raw.cities.length ? raw.cities : [raw.city].filter(Boolean);
  const title = String(raw.title).trim();
  const regions = classifyRegions(cities, raw.region);
  return {
    id: jobKey(companyId, raw.url),
    title,
    companyId,
    companyName: company?.name ?? raw.firm,
    firmType: company?.type ?? raw.firmType ?? '',
    location: cities.join(' / '),
    region: regions[0],
    regions,
    category: classifyCategory(title, { wsqRole: raw.role }) ?? 'Software Eng',
    seniority: classifySeniority(title, raw.xp),
    wsqRole: raw.role || '',
    salary: formatSalary(raw.salary),
    postedAt: isoOrNull(raw.postedAt),
    url: raw.url,
    tags: techTags(title),
  };
}

function atsToJob(raw, company) {
  if (!isHttpUrl(raw.url)) return null;
  const title = String(raw.title || '').trim();
  const category = classifyCategory(title, { strict: company.filter === 'strict' });
  if (!category) return null;
  const location = String(raw.location || '').trim();
  const regions = classifyRegions(location);
  return {
    id: jobKey(company.id, raw.url),
    title,
    companyId: company.id,
    companyName: company.name,
    firmType: company.type,
    location,
    region: regions[0],
    regions,
    category,
    seniority: classifySeniority(title),
    salary: formatSalary(raw.salary),
    postedAt: isoOrNull(raw.postedAt),
    url: raw.url,
    tags: techTags(title, raw.description),
  };
}

// ── Runs ──────────────────────────────────────────────────────────────────

function logRun(paths, row) {
  mkdirSync(paths.dir, { recursive: true });
  if (!existsSync(paths.runs)) appendFileSync(paths.runs, 'at\tsource\tcompany\tstatus\tfetched\tkept\tadded\tclosed\tms\terror\n');
  const clean = (v) => String(v ?? '').replace(/[\t\n]/g, ' ');
  appendFileSync(paths.runs, [row.at, row.source, row.company, row.status, row.fetched, row.kept, row.added, row.closed, row.ms, row.error].map(clean).join('\t') + '\n');
}

async function runIngestWsq({ quiet = false } = {}) {
  const paths = dataPaths();
  const registry = loadRegistry();
  const companyByWsq = new Map();
  const renames = new Map();
  for (const c of registry) {
    for (const alias of c.wsq) {
      companyByWsq.set(alias, c);
      renames.set(wsqFallbackId(alias), c);
    }
  }
  const t0 = Date.now();
  const now = new Date().toISOString();
  const raw = await fetchWsq();
  const unmapped = [...new Set(raw.map((r) => r.firm).filter((f) => !companyByWsq.has(f)))];
  const jobs = raw.map((r) => wsqToJob(r, companyByWsq)).filter(Boolean);
  const store = readJson(paths.jobs, emptyStore());
  const state = readJson(paths.state, emptyState());
  const migrated = migrateCompanyIds(store, state, renames);
  if (migrated.tracked) writeJsonAtomic(paths.state, state);
  const res = applySourceRun(store, 'wsq', dedupeById(jobs), now);
  writeJsonAtomic(paths.jobs, store);
  logRun(paths, { at: now, source: 'wsq', company: '*', status: 'ok', fetched: raw.length, kept: res.total, added: res.added, closed: res.gone, ms: Date.now() - t0 });
  if (!quiet) {
    console.log(`wsq: ${raw.length} listings, ${res.added} new, ${res.gone} closed`);
    if (migrated.jobs) console.log(`wsq: moved ${migrated.jobs} jobs (${migrated.tracked} tracked) from wsq-* ids to their companies.yml ids`);
    if (unmapped.length) console.log(`wsq: firms not in companies.yml (given a wsq-* id; add them): ${unmapped.join(', ')}`);
  }
  return { ...res, fetched: raw.length, unmapped };
}

function dedupeById(jobs) {
  const byId = new Map();
  for (const j of jobs) {
    const prev = byId.get(j.id);
    byId.set(j.id, prev ? { ...prev, tags: [...new Set([...prev.tags, ...j.tags])] } : j);
  }
  return [...byId.values()];
}

async function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error(`${label}: timed out after ${ms / 1000}s`)), ms); });
  try { return await Promise.race([promise, timeout]); } finally { clearTimeout(timer); }
}

async function runScan({ only = null, quiet = false } = {}) {
  const paths = dataPaths();
  const registry = loadRegistry();
  const targets = registry.filter((c) => c.boards.length && (!only || c.id === only));
  if (only && !targets.length) throw new Error(`no company "${only}" with a board in companies.yml`);
  const { loadProviders, resolveProvider } = await import('../providers/_registry.mjs');
  const { makeHttpCtx } = await import('../providers/_http.mjs');
  const providers = await loadProviders(join(REPO, 'providers'));
  const ctx = makeHttpCtx();

  const store = readJson(paths.jobs, emptyStore());
  const trackedIds = new Set(Object.keys(readJson(paths.state, emptyState()).jobs));
  const summary = [];
  let cursor = 0;
  const worker = async () => {
    while (cursor < targets.length) {
      const company = targets[cursor++];
      for (const board of company.boards) {
        const t0 = Date.now();
        const now = new Date().toISOString();
        const sourceKey = `ats:${board}`;
        const row = { at: now, source: sourceKey, company: company.id, fetched: 0, kept: 0, added: 0, closed: 0, ms: 0, error: '' };
        try {
          const entry = { name: company.name, careers_url: board };
          const hit = resolveProvider(entry, providers, { skipIds: ['local-parser'] });
          if (!hit || hit.error) throw new Error(hit?.error || 'no provider recognizes this board URL');
          const raw = await withTimeout(hit.provider.fetch(entry, ctx), BOARD_TIMEOUT_MS, `${company.id} ${hit.provider.id}`);
          const listed = raw.filter((r) => r?.title && r?.url);
          const kept = dedupeById(listed.map((r) => atsToJob(r, company)).filter(Boolean));
          // Still listed but not a relevant role (e.g. after a classifier change):
          // drop it, unless WSQ curates it or you are tracking it - then it just
          // stays seen on this board instead of looking closed.
          const keptIds = new Set(kept.map((j) => j.id));
          for (const id of new Set(listed.map((r) => jobKey(company.id, r.url)))) {
            const prev = store.jobs[id];
            if (keptIds.has(id) || !prev) continue;
            if (prev.sources?.wsq || trackedIds.has(id)) kept.push({ ...prev, category: classifyCategory(prev.title, { wsqRole: prev.wsqRole }) ?? prev.category });
            else delete store.jobs[id];
          }
          const res = applySourceRun(store, sourceKey, kept, now, (j) => j.companyId === company.id);
          Object.assign(row, { status: 'ok', provider: hit.provider.id, fetched: raw.length, kept: kept.length, added: res.added, closed: res.gone });
        } catch (err) {
          Object.assign(row, { status: 'error', error: String(err?.message || err).slice(0, 300) });
        }
        row.ms = Date.now() - t0;
        store.companyRuns[company.id] = { ...(store.companyRuns[company.id] || {}), [board]: { at: row.at, status: row.status, fetched: row.fetched, kept: row.kept, error: row.error } };
        logRun(paths, row);
        summary.push(row);
        if (!quiet) console.log(`${row.status === 'ok' ? 'ok ' : 'ERR'} ${company.id.padEnd(20)} fetched=${String(row.fetched).padStart(5)} kept=${String(row.kept).padStart(4)} new=${String(row.added).padStart(4)} closed=${row.closed}${row.error ? `  ${row.error}` : ''}`);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(SCAN_CONCURRENCY, targets.length) }, worker));
  writeJsonAtomic(paths.jobs, store);
  return summary;
}

// ── Views ─────────────────────────────────────────────────────────────────

function loadView() {
  const paths = dataPaths();
  const store = readJson(paths.jobs, emptyStore());
  const state = readJson(paths.state, emptyState());
  const registry = loadRegistry();
  const jobs = Object.values(store.jobs).map((j) => ({ ...j, status: state.jobs[j.id]?.status || 'Not Applied' }));
  for (const m of state.manual || []) if (!store.jobs[m.id]) jobs.push({ ...m, manual: true, active: true, status: state.jobs[m.id]?.status || 'Not Applied' });
  return { paths, store, state, registry, jobs };
}

export function companyRollup(registry, jobs, companyRuns = {}) {
  const byId = new Map(registry.map((c) => [c.id, { ...c, open: 0, notApplied: 0, applied: 0, closed: 0, scan: 'none' }]));
  for (const j of jobs) {
    if (!byId.has(j.companyId)) byId.set(j.companyId, { id: j.companyId, name: j.companyName, type: j.firmType, wsq: [], boards: [], website: '', filter: 'all', open: 0, notApplied: 0, applied: 0, closed: 0, scan: 'none' });
    const c = byId.get(j.companyId);
    if (!j.active) { c.closed++; continue; }
    c.open++;
    if (j.status === 'Not Applied') c.notApplied++;
    if (['Applied', 'Interviewing', 'Offer', 'Rejected'].includes(j.status)) c.applied++;
  }
  for (const c of byId.values()) {
    const runs = Object.values(companyRuns[c.id] || {});
    if (!c.boards.length) c.scan = 'wsq-only';
    else if (!runs.length) c.scan = 'not scanned';
    else c.scan = runs.every((r) => r.status === 'ok') ? 'ok' : runs.some((r) => r.status === 'ok') ? 'partial' : 'error';
    c.lastScan = runs.map((r) => r.at).sort().pop() || null;
    c.scanErrors = runs.filter((r) => r.status !== 'ok').map((r) => r.error);
  }
  return [...byId.values()].sort((a, b) => b.open - a.open || a.name.localeCompare(b.name));
}

function writeCompaniesMd(paths, companies) {
  const lines = [
    '# Job board - company directory',
    '',
    `Generated by \`node jobboard/jobboard.mjs\` on ${new Date().toISOString().slice(0, 10)}. Open roles = relevant, still-listed postings.`,
    '',
    '| Company | Type | Open roles | Not applied | Applied | Source | Careers |',
    '|---|---|---:|---:|---:|---|---|',
    ...companies.map((c) => `| ${c.name} | ${c.type} | ${c.open} | ${c.notApplied} | ${c.applied} | ${c.scan === 'wsq-only' ? 'WSQ only' : `ATS (${c.scan})`} | ${c.website ? `[link](${c.website})` : ''} |`),
    '',
  ];
  mkdirSync(paths.dir, { recursive: true });
  writeFileSync(paths.companiesMd, lines.join('\n'), 'utf-8');
}

function countBy(items, key) {
  const out = {};
  for (const it of items) out[it[key]] = (out[it[key]] || 0) + 1;
  return out;
}

function printSummary() {
  const { store, jobs, registry, paths } = loadView();
  if (!Object.keys(store.jobs).length) {
    console.log('jobboard: 0 jobs yet.');
    console.log('next: node jobboard/jobboard.mjs refresh   (WSQ + every company board, ~3 min)');
    return;
  }
  const active = jobs.filter((j) => j.active);
  const companies = companyRollup(registry, jobs, store.companyRuns);
  const fmt = (o) => Object.entries(o).sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}=${v}`).join(' ');
  console.log(`jobboard: ${active.length} open roles at ${companies.filter((c) => c.open).length} companies (updated ${store.updatedAt?.slice(0, 16).replace('T', ' ')} UTC)`);
  console.log(`status: ${fmt(countBy(active, 'status'))}`);
  console.log(`category: ${fmt(countBy(active, 'category'))}`);
  console.log(`firm type: ${fmt(countBy(active, 'firmType'))}`);
  console.log(`closed since first seen: ${jobs.filter((j) => !j.active).length}`);
  const errs = companies.filter((c) => c.scan === 'error' || c.scan === 'partial');
  if (errs.length) console.log(`scan errors: ${errs.map((c) => c.id).join(', ')}  (details: ${paths.runs})`);
  console.log('next: node jobboard/jobboard.mjs serve --open   |   list --status "Not Applied" --category "Quant Dev" --region USA');
}

function parseFlags(argv) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const k = a.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith('--')) { flags[k] = next; i++; } else flags[k] = true;
    } else positional.push(a);
  }
  return { flags, positional };
}

function printList(flags) {
  const { jobs } = loadView();
  const q = String(flags.q || '').toLowerCase();
  const eq = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
  const rows = jobs
    .filter((j) => flags.closed || j.active)
    .filter((j) => !flags.status || eq(j.status, flags.status))
    .filter((j) => !flags.category || eq(j.category, flags.category))
    .filter((j) => !flags.company || eq(j.companyId, flags.company))
    .filter((j) => !flags.type || eq(j.firmType, flags.type))
    .filter((j) => !flags.region || (j.regions || [j.region]).some((r) => eq(r, flags.region)))
    .filter((j) => !q || `${j.title} ${j.companyName} ${j.location}`.toLowerCase().includes(q))
    .sort((a, b) => String(b.postedAt || '').localeCompare(String(a.postedAt || '')) || String(b.firstSeen).localeCompare(String(a.firstSeen)));
  const limit = flags.full ? rows.length : Number(flags.limit || 25);
  console.log(`jobs[${rows.length}]{id,status,company,title,category,location,posted}:`);
  for (const j of rows.slice(0, limit)) {
    console.log(`  ${j.id},${j.status},${j.companyName},${JSON.stringify(j.title)},${j.category},${JSON.stringify(j.location)},${(j.postedAt || '').slice(0, 10)}`);
  }
  if (rows.length > limit) console.log(`  ... ${rows.length - limit} more (--limit N or --full)`);
  if (!rows.length) console.log('  0 results');
}

export function applyStatePatch(state, id, patch, now = new Date().toISOString()) {
  if (patch.status !== undefined && !STATUSES.includes(patch.status)) throw new Error(`status must be one of: ${STATUSES.join(', ')}`);
  if (patch.notes !== undefined && String(patch.notes).length > NOTES_MAX) throw new Error(`notes longer than ${NOTES_MAX} chars`);
  const prev = state.jobs[id] || { status: 'Not Applied', history: [] };
  const next = { ...prev, updatedAt: now };
  if (patch.status !== undefined && patch.status !== prev.status) {
    next.status = patch.status;
    next.history = [...(prev.history || []), { at: now, from: prev.status, to: patch.status }];
    if (patch.status === 'Applied' && !prev.appliedAt) next.appliedAt = now;
  }
  if (patch.notes !== undefined) next.notes = String(patch.notes);
  if (patch.starred !== undefined) next.starred = Boolean(patch.starred);
  if (patch.appliedAt !== undefined) next.appliedAt = isoOrNull(patch.appliedAt);
  state.jobs[id] = next;
  return next;
}

function runMark(positional, flags) {
  const [id, ...statusWords] = positional;
  const status = statusWords.join(' ');
  if (!id || !status) throw new Error('usage: mark <jobId> <status> [--note text]');
  const { paths, state, jobs } = loadView();
  if (!jobs.some((j) => j.id === id)) throw new Error(`no job with id "${id}" (find ids with: list --q <text>)`);
  const rec = applyStatePatch(state, id, { status, ...(flags.note ? { notes: flags.note } : {}) });
  writeJsonAtomic(paths.state, state);
  console.log(`marked ${id} -> ${rec.status}`);
}

// ── Server ────────────────────────────────────────────────────────────────

function serve({ port, open }) {
  let refresh = { running: false, startedAt: null, finishedAt: null, exitCode: null, log: '' };

  const send = (res, code, body, type = 'application/json; charset=utf-8') => {
    res.writeHead(code, { 'content-type': type, 'cache-control': 'no-store', 'x-content-type-options': 'nosniff' });
    res.end(typeof body === 'string' ? body : JSON.stringify(body));
  };
  const readBody = (req) => new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > 64 * 1024) { reject(new Error('body too large')); req.destroy(); } else chunks.push(c);
    });
    req.on('end', () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString('utf-8') || '{}')); } catch { reject(new Error('invalid JSON body')); }
    });
    req.on('error', reject);
  });

  const allowedHosts = new Set([`127.0.0.1:${port}`, `localhost:${port}`]);

  const server = createServer(async (req, res) => {
    // Loopback-only server; still refuse foreign Host headers (DNS rebinding)
    // and cross-origin writes (a page on another site POSTing to localhost).
    if (!allowedHosts.has(String(req.headers.host))) return send(res, 403, { error: 'forbidden host' });
    if (req.method === 'POST') {
      const origin = req.headers.origin;
      if (origin && !allowedHosts.has(origin.replace(/^https?:\/\//, ''))) return send(res, 403, { error: 'forbidden origin' });
      if (!String(req.headers['content-type'] || '').startsWith('application/json')) return send(res, 415, { error: 'json only' });
    }
    const url = new URL(req.url, `http://${req.headers.host}`);
    try {
      if (req.method === 'GET' && url.pathname === '/') return send(res, 200, readFileSync(UI_PATH, 'utf-8'), 'text/html; charset=utf-8');
      if (req.method === 'GET' && url.pathname === '/api/data') {
        const { store, state, registry, jobs } = loadView();
        return send(res, 200, {
          updatedAt: store.updatedAt,
          statuses: STATUSES,
          categories: CATEGORIES,
          seniorities: SENIORITIES,
          jobs: jobs.map((j) => ({ ...j, state: state.jobs[j.id] || null })),
          companies: companyRollup(registry, jobs, store.companyRuns),
        });
      }
      if (req.method === 'POST' && url.pathname === '/api/state') {
        const body = await readBody(req);
        const { paths, state, jobs } = loadView();
        if (!jobs.some((j) => j.id === body.id)) return send(res, 404, { error: 'unknown job id' });
        const rec = applyStatePatch(state, body.id, body.patch || {});
        writeJsonAtomic(paths.state, state);
        return send(res, 200, { id: body.id, state: rec });
      }
      if (req.method === 'POST' && url.pathname === '/api/manual') {
        const body = await readBody(req);
        const title = String(body.title || '').trim();
        const companyName = String(body.companyName || '').trim();
        const jobUrl = String(body.url || '').trim();
        if (!title || !companyName || !isHttpUrl(jobUrl)) return send(res, 400, { error: 'title, company and an http(s) url are required' });
        const { paths, store, state, registry } = loadView();
        const company = registry.find((c) => c.name.toLowerCase() === companyName.toLowerCase() || c.id === companyName.toLowerCase());
        const companyId = company?.id ?? `manual-${companyName.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
        const id = `${jobKey(companyId, jobUrl)}`;
        if (store.jobs[id] || (state.manual || []).some((m) => m.id === id)) return send(res, 409, { error: 'already on the board' });
        const location = String(body.location || '').trim();
        const regions = classifyRegions(location);
        const now = new Date().toISOString();
        const job = {
          id, title, companyId, companyName: company?.name ?? companyName, firmType: company?.type ?? String(body.firmType || 'Other'),
          location, region: regions[0], regions, category: classifyCategory(title) ?? 'Software Eng',
          seniority: classifySeniority(title), salary: String(body.salary || ''), postedAt: null, url: jobUrl,
          tags: techTags(title), sources: { manual: { url: jobUrl, seenAt: now, gone: false } }, firstSeen: now,
        };
        state.manual = [...(state.manual || []), job];
        if (body.status) applyStatePatch(state, id, { status: body.status }, now);
        writeJsonAtomic(paths.state, state);
        return send(res, 200, { job });
      }
      if (url.pathname === '/api/refresh') {
        if (req.method === 'POST' && !refresh.running) {
          refresh = { running: true, startedAt: new Date().toISOString(), finishedAt: null, exitCode: null, log: '' };
          const child = spawn(process.execPath, [fileURLToPath(import.meta.url), 'refresh'], { cwd: REPO, env: process.env });
          const onData = (d) => { refresh.log = (refresh.log + d.toString()).slice(-20_000); };
          child.stdout.on('data', onData);
          child.stderr.on('data', onData);
          child.on('close', (code) => Object.assign(refresh, { running: false, exitCode: code, finishedAt: new Date().toISOString() }));
        }
        return send(res, 200, refresh);
      }
      return send(res, 404, { error: 'not found' });
    } catch (err) {
      return send(res, 400, { error: String(err?.message || err) });
    }
  });
  server.listen(port, '127.0.0.1', () => {
    const link = `http://127.0.0.1:${port}/`;
    console.log(`jobboard: serving ${link}  (Ctrl+C to stop)`);
    if (open) spawn('open', [link], { stdio: 'ignore', detached: true }).unref();
  });
}

// ── Self-test ─────────────────────────────────────────────────────────────

function selfTest() {
  let passed = 0;
  const failures = [];
  const check = (name, actual, expected) => {
    const ok = JSON.stringify(actual) === JSON.stringify(expected);
    if (ok) passed++; else failures.push(`${name}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  };

  // Category
  check('qd low latency', classifyCategory('Senior C++ Low Latency Engineer'), 'Quant Dev');
  check('qd quant developer', classifyCategory('Quantitative Developer'), 'Quant Dev');
  check('qr', classifyCategory('Graduate Quantitative Researcher, PhD (2027 Start)'), 'Quant Research');
  check('qr trader', classifyCategory('Quantitative Trader'), 'Trading');
  check('ai', classifyCategory('Machine Learning Engineer, LLM Platform'), 'AI/ML');
  check('swe', classifyCategory('Software Engineer, Backend (Python)'), 'Software Eng');
  check('sre', classifyCategory('Senior Cluster Site Reliability Engineer'), 'Software Eng');
  check('data', classifyCategory('Data Analyst - Equities'), 'Data');
  check('recruiter dropped', classifyCategory('Technical Recruiter'), null);
  check('receptionist dropped', classifyCategory('Receptionist'), null);
  check('sales engineer dropped', classifyCategory('Sales Engineer'), null);
  check('strict drops generic', classifyCategory('Senior Wealth Advisor', { strict: true }), null);
  check('strict drops plain swe', classifyCategory('Software Engineer III', { strict: true }), null);
  check('strict keeps python swe', classifyCategory('Software Engineer III - Python', { strict: true }), 'Software Eng');
  check('wsq fallback', classifyCategory('Operations Analyst', { wsqRole: 'Dev' }), 'Software Eng');
  check('research engineer is not QR-only', classifyCategory('AI Research Engineer'), 'AI/ML');
  check('qd inside QTR title', classifyCategory('Quantitative Trading & Research - Rates - Quantitative Developer - Vice President'), 'Quant Dev');
  check('ai pmo dropped', classifyCategory('AI Enablement PMO Director'), null);
  check('ai growth dropped', classifyCategory('Growth & AI Initiatives Manager'), null);
  check('ai architect kept', classifyCategory('AI Application Architect'), 'AI/ML');
  check('applied ai researcher', classifyCategory('Senior Applied AI Researcher, Vice President'), 'AI/ML');
  check('quant recruiter dropped', classifyCategory('Lead Technical Recruiter (Quant Engineering)'), null);
  check('execution analyst dropped', classifyCategory('Campaign Execution Analyst'), null);
  check('execution trading', classifyCategory('Associate, Execution Trading, BlackRock Global Markets (BGM)'), 'Trading');
  check('market data eng', classifyCategory('Engineering Manager, Market Data & Analytics'), 'Quant Dev');
  check('infra trading eng', classifyCategory('Senior Infrastructure Engineer, Trading'), 'Software Eng');
  check('quantexa solution eng dropped', classifyCategory('Solution Engineer - Quantexa Platform'), null);
  check('qr low latency', classifyCategory('Quantitative Researcher - Low Latency'), 'Quant Research');
  check('systematic trading intern', classifyCategory('2027 Summer Internship Program - Systematic Trading, London'), 'Quant Research');
  check('fpga', classifyCategory('FPGA Engineer'), 'Quant Dev');
  check('surveillance dropped', classifyCategory('Trading Floor Surveillance Analyst'), null);
  check('product strategy dropped', classifyCategory('AVP. Product Strategy - Trading'), null);

  // Seniority / region / tags
  check('intern', classifySeniority('Quantitative Research Internship - Summer 2027'), 'Intern');
  check('new grad', classifySeniority('Software Engineer - New Grad'), 'New Grad');
  check('senior', classifySeniority('Staff Software Engineer'), 'Senior+');
  check('wsq xp', classifySeniority('Quant Researcher', 'Entry Lvl'), 'Entry');
  check('region nyc', classifyRegions('New York, NY'), ['USA']);
  check('region london', classifyRegions('London, UK'), ['Europe']);
  check('region jersey city', classifyRegions('Jersey City, NJ'), ['USA']);
  check('region india', classifyRegions('Gurugram'), ['India']);
  check('region multi-city', classifyRegions('New York / Toronto'), ['USA', 'Canada']);
  check('region separators', classifyRegions('London; Singapore | Chicago · Mumbai or Dubai'), ['Europe', 'Asia-Pacific', 'USA', 'India', 'Middle East']);
  check('region vague', [classifyRegions('2 Locations'), classifyRegions(''), classifyRegions('Mars')], [['Multiple'], ['Unknown'], ['Other']]);
  check('region wsq', classifyRegions(['x'], 'Europe'), ['Europe']);
  check('region wsq unions cities', classifyRegions(['London', 'New York'], 'Europe'), ['Europe', 'USA']);
  check('region wsq north america montreal', classifyRegions(['Montreal'], 'North America'), ['Canada']);
  check('region wsq north america sao paulo', classifyRegions(['Sao Paulo'], 'North America'), ['Latin America']);
  check('region wsq north america new york', classifyRegions(['New York'], 'North America'), ['USA']);
  check('region wsq global uses cities', classifyRegions(['Montreal'], 'Global'), ['Canada']);
  check('region wsq global without cities', classifyRegions([], 'Global'), ['Unknown']);
  check('tags', techTags('Senior C++ Developer', 'Python and kdb+ required, low-latency'), ['C++', 'Python', 'KDB/q', 'Low Latency']);

  // External ids: WSQ's firm-domain link and the ATS link collapse together.
  check('gh_jid', externalId('https://www.optiver.com/join-us/jobs/8451764002/?gh_jid=8451764002'), 'gh-8451764002');
  check('gh board', externalId('https://job-boards.greenhouse.io/optiverus/jobs/8451764002'), 'gh-8451764002');
  check('jane street position', externalId('https://www.janestreet.com/join-jane-street/position/8573726002'), 'gh-8573726002');
  check('akuna job path', externalId('https://www.akunacapital.com/careers/job/7986086/?gh_jid=7986086'), 'gh-7986086');
  check('lever', externalId('https://jobs.lever.co/wintermute-trading/d962dc39-8839-4e13-a37a-baba49e52b44'), 'uuid-d962dc39-8839-4e13-a37a-baba49e52b44');
  check('workday', externalId('https://gresearch.wd103.myworkdayjobs.com/en-US/G-Research/job/London-UK/Platform-Desktop-Engineering-Manager_R3738'), 'wd-R3738');
  check('workday suffix', externalId('https://arrowstreetcapital.wd5.myworkdayjobs.com/en-US/Arrowstreet/job/Boston/Pre-Trade-Investment-Services_R1511-1'), 'wd-R1511');
  check('workday dashed id', externalId('https://wd1.myworkdaysite.com/en-US/recruiting/wf/WellsFargoJobs/job/Charlotte-NC/Quantitative-Analytics-Specialist_R-533492'), 'wd-R-533492');
  check('workday dashed JR id', externalId('https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays/job/London/Quant-Developer_JR-0000098158'), 'wd-JR-0000098158');
  check('workday dashed id suffix', externalId('https://barclays.wd3.myworkdayjobs.com/en-US/External_Career_Site_Barclays/job/London/Quant-Developer_JR-0000114814-1'), 'wd-JR-0000114814');
  check('workday dashed ids stay distinct', externalId('https://statestreet.wd1.myworkdayjobs.com/en-US/Global/job/Boston/A_R-771234') === externalId('https://statestreet.wd1.myworkdayjobs.com/en-US/Global/job/Boston/B_R-771235'), false);
  check('eightfold', externalId('https://mlp.eightfold.ai/careers/job/755958015047'), 'job-755958015047');
  check('no id', externalId('https://www.rentec.com/Careers.action?jobs=true&selectedPosition=x'), null);
  check('jobKey fallback stable', jobKey('rentec', 'https://www.rentec.com/Careers.action?selectedPosition=x#top'), jobKey('rentec', 'https://rentec.com/Careers.action?selectedPosition=x'));

  // WSQ parser against a synthetic RSC stream.
  const listing = { id: 'a', title: 'Quant Dev', firm: 'Optiver', firmType: 'Prop Trading', city: 'Chicago', region: 'USA', cities: ['Chicago'], role: 'Dev', xp: 'Mid-Senior', salary: '$$1 - $2', url: 'https://x.test/jobs/1234567', postedAt: '2026-09-01T00:00:00Z' };
  const rsc = `5:["$","main",null,{"children":["$","$L13",null,{"jobs":${JSON.stringify([listing])},"filterMenu":{"firm":["]"]}}]}]`;
  const html = `<script>self.__next_f.push([1,${JSON.stringify(rsc.slice(0, 40))}])</script><script>self.__next_f.push([1,${JSON.stringify(rsc.slice(40))}])</script>`;
  const parsed = parseWsqHtml(html);
  check('wsq parse count', parsed.length, 1);
  check('wsq parse title', parsed[0]?.title, 'Quant Dev');
  let threw = false;
  try { parseWsqHtml('<html></html>'); } catch { threw = true; }
  check('wsq parse fails loudly on layout change', threw, true);
  const wj = wsqToJob(listing, new Map([['Optiver', { id: 'optiver', name: 'Optiver', type: 'Prop Trading' }]]));
  check('wsq salary cleaned', wj.salary, '$1 - $2');
  check('wsq job id', wj.id, 'optiver:gh-1234567');
  const multi = wsqToJob({ ...listing, region: 'North America', cities: ['Montreal', 'London', 'Singapore'] }, new Map());
  check('wsq multi-city regions', [multi.region, multi.regions], ['Canada', ['Canada', 'Europe', 'Asia-Pacific']]);
  check('wsq drops javascript url', wsqToJob({ ...listing, url: 'javascript:alert(1)' }, new Map()), null);
  check('wsq drops data url', wsqToJob({ ...listing, url: 'data:text/html,x' }, new Map()), null);
  const atsCo = { id: 'optiver', name: 'Optiver', type: 'Prop Trading', filter: 'all' };
  check('ats drops javascript url', atsToJob({ title: 'Quantitative Developer', url: 'javascript:alert(1)' }, atsCo), null);
  check('ats keeps https url', atsToJob({ title: 'Quantitative Developer', url: 'https://jobs.lever.co/x/d962dc39-8839-4e13-a37a-baba49e52b44' }, atsCo)?.category, 'Quant Dev');

  // Mapping a WSQ fallback firm moves its jobs and tracked state to the registry id.
  const fallback = wsqToJob({ ...listing, firm: 'Foo Capital' }, new Map());
  check('wsq fallback id', fallback.id, 'wsq-foo-capital:gh-1234567');
  const mStore = emptyStore();
  const mState = emptyState();
  mStore.jobs[fallback.id] = { ...fallback, firstSeen: 't0' };
  mStore.jobs['wsq-foo-capital:gh-2'] = { id: 'wsq-foo-capital:gh-2', companyId: 'wsq-foo-capital', firstSeen: 't0' };
  mStore.jobs['foo:gh-2'] = { id: 'foo:gh-2', companyId: 'foo', firstSeen: 't1' };
  mStore.jobs['other:gh-3'] = { id: 'other:gh-3', companyId: 'other' };
  mState.jobs[fallback.id] = { status: 'Applied' };
  mState.jobs['wsq-foo-capital:gh-2'] = { status: 'Saved' };
  mState.jobs['foo:gh-2'] = { status: 'Interviewing' };
  const foo = { id: 'foo', name: 'Foo Capital', type: 'Hedge Fund' };
  const mig = migrateCompanyIds(mStore, mState, new Map([['wsq-foo-capital', foo]]));
  check('migrate counts', mig, { jobs: 2, tracked: 1 });
  check('migrate store rekeyed', Object.keys(mStore.jobs).sort(), ['foo:gh-1234567', 'foo:gh-2', 'other:gh-3']);
  check('migrate store fields', [mStore.jobs['foo:gh-1234567'].id, mStore.jobs['foo:gh-1234567'].companyId, mStore.jobs['foo:gh-1234567'].companyName, mStore.jobs['foo:gh-1234567'].firstSeen], ['foo:gh-1234567', 'foo', 'Foo Capital', 't0']);
  check('migrate keeps existing store record', mStore.jobs['foo:gh-2'].firstSeen, 't1');
  check('migrate moves state', [mState.jobs['foo:gh-1234567']?.status, mState.jobs[fallback.id]], ['Applied', undefined]);
  check('migrate never overwrites new-id state', [mState.jobs['foo:gh-2'].status, mState.jobs['wsq-foo-capital:gh-2'].status], ['Interviewing', 'Saved']);
  check('migrate idempotent', migrateCompanyIds(mStore, mState, new Map([['wsq-foo-capital', foo]])), { jobs: 0, tracked: 0 });
  check('wsq job lands on migrated id', wsqToJob({ ...listing, firm: 'Foo Capital' }, new Map([['Foo Capital', foo]])).id, 'foo:gh-1234567');

  // Merge: dedupe across sources, gone/closed only on successful runs, reopen.
  const store = emptyStore();
  const a = { id: 'x:gh-1', companyId: 'x', title: 'A', url: 'u1', tags: ['C++'] };
  const b = { id: 'x:gh-2', companyId: 'x', title: 'B', url: 'u2', tags: [] };
  applySourceRun(store, 'wsq', [a, b], 't1');
  applySourceRun(store, 'ats:x', [{ ...a, salary: '$9', tags: ['Python'] }], 't2', (j) => j.companyId === 'x');
  check('merge keeps both sources', Object.keys(store.jobs['x:gh-1'].sources).sort(), ['ats:x', 'wsq']);
  check('merge unions tags', store.jobs['x:gh-1'].tags, ['C++', 'Python']);
  check('ats absence alone does not close a wsq-live job', store.jobs['x:gh-2'].active, true);
  const r = applySourceRun(store, 'wsq', [a], 't3');
  check('closed when last source drops it', [store.jobs['x:gh-2'].active, store.jobs['x:gh-2'].closedAt, r.gone], [false, 't3', 1]);
  check('still active via ats', store.jobs['x:gh-1'].active, true);
  applySourceRun(store, 'wsq', [a, b], 't4');
  check('reopens when listed again', [store.jobs['x:gh-2'].active, store.jobs['x:gh-2'].closedAt], [true, null]);
  check('firstSeen preserved', store.jobs['x:gh-2'].firstSeen, 't1');
  applySourceRun(store, 'ats:y', [], 't5', (j) => j.companyId === 'y');
  check('out-of-scope jobs untouched', store.jobs['x:gh-1'].active, true);
  applySourceRun(store, 'wsq', [a, { ...b, title: 'B renamed', category: 'Quant Research' }], 't6');
  check('wsq updates its own jobs', [store.jobs['x:gh-2'].title, store.jobs['x:gh-2'].category], ['B renamed', 'Quant Research']);
  applySourceRun(store, 'wsq', [{ ...a, title: 'A from wsq' }, b], 't7');
  check('wsq defers to a live ats record', store.jobs['x:gh-1'].title, 'A');
  const rStore = emptyStore();
  const rJob = { id: 'r:gh-1', companyId: 'r', title: 'R', url: 'u', tags: [] };
  applySourceRun(rStore, 'wsq', [{ ...rJob, region: 'USA', regions: ['USA', 'Canada'] }], 't1');
  applySourceRun(rStore, 'ats:r', [{ ...rJob, region: 'Multiple', regions: ['Multiple'] }], 't2');
  check('merge keeps specific regions over vague', [rStore.jobs['r:gh-1'].region, rStore.jobs['r:gh-1'].regions], ['USA', ['USA', 'Canada']]);
  applySourceRun(rStore, 'ats:r', [{ ...rJob, region: 'Europe', regions: ['Europe'] }], 't3');
  check('merge unions regions across sources', [rStore.jobs['r:gh-1'].region, rStore.jobs['r:gh-1'].regions], ['Europe', ['Europe', 'USA', 'Canada']]);

  // State patches.
  const st = emptyState();
  applyStatePatch(st, 'j1', { status: 'Applied' }, 'T1');
  check('applied sets appliedAt', st.jobs.j1.appliedAt, 'T1');
  applyStatePatch(st, 'j1', { status: 'Interviewing' }, 'T2');
  check('history recorded', st.jobs.j1.history.map((h) => h.to), ['Applied', 'Interviewing']);
  check('appliedAt kept', st.jobs.j1.appliedAt, 'T1');
  threw = false;
  try { applyStatePatch(st, 'j1', { status: 'Bogus' }); } catch { threw = true; }
  check('invalid status refused', threw, true);

  // Registry sanity.
  const reg = loadRegistry();
  check('registry has ids', reg.every((c) => /^[a-z0-9-]+$/.test(c.id)), true);
  check('registry boards are https', reg.every((c) => c.boards.every((b) => b.startsWith('https://'))), true);

  if (failures.length) {
    for (const f of failures) console.error(`FAIL ${f}`);
    console.error(`FAIL ${failures.length}/${passed + failures.length} self-test checks`);
    return 1;
  }
  console.log(`PASS ${passed}/${passed} self-test checks`);
  return 0;
}

// ── Main ──────────────────────────────────────────────────────────────────

async function main(argv) {
  const { flags, positional } = parseFlags(argv);
  const cmd = positional.shift();
  if (flags['self-test']) return selfTest();
  if (flags.help || flags.h) { console.log(readFileSync(fileURLToPath(import.meta.url), 'utf-8').split('USAGE')[1].split('*/')[0].replace(/^ \* ?/gm, '')); return 0; }
  switch (cmd) {
    case undefined: printSummary(); return 0;
    case 'ingest-wsq': await runIngestWsq(); break;
    case 'scan': await runScan({ only: typeof flags.company === 'string' ? flags.company : null }); break;
    case 'refresh': {
      let wsqFailed = false;
      try { await runIngestWsq(); } catch (err) {
        wsqFailed = true;
        console.error(`wsq: FAILED - ${err.message}`);
        logRun(dataPaths(), { at: new Date().toISOString(), source: 'wsq', company: '*', status: 'error', error: err.message });
      }
      const rows = await runScan();
      const errors = rows.filter((r) => r.status !== 'ok');
      console.log(`scan: ${rows.length - errors.length}/${rows.length} boards ok${errors.length ? `; failed: ${errors.map((r) => r.company).join(', ')}` : ''}`);
      if (wsqFailed || errors.length) process.exitCode = 2;
      break;
    }
    case 'serve': serve({ port: Number(flags.port || DEFAULT_PORT), open: Boolean(flags.open) }); return null;
    case 'list': printList(flags); return 0;
    case 'mark': runMark(positional, flags); return 0;
    case 'companies': {
      const { registry, jobs, store } = loadView();
      const rows = companyRollup(registry, jobs, store.companyRuns);
      console.log(`companies[${rows.length}]{id,name,type,open,notApplied,applied,source}:`);
      for (const c of rows) console.log(`  ${c.id},${c.name},${c.type},${c.open},${c.notApplied},${c.applied},${c.scan}`);
      return 0;
    }
    default:
      console.error(`unknown command "${cmd}". Commands: refresh, ingest-wsq, scan, serve, list, mark, companies, --self-test`);
      return 1;
  }
  const { registry, jobs, store, paths } = loadView();
  writeCompaniesMd(paths, companyRollup(registry, jobs, store.companyRuns));
  printSummary();
  return process.exitCode ?? 0;
}

const invokedDirectly = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (invokedDirectly) {
  main(process.argv.slice(2)).then((code) => { if (code !== null && code !== undefined) process.exitCode = code; }).catch((err) => {
    console.error(`jobboard: ${err.message}`);
    process.exitCode = 1;
  });
}
