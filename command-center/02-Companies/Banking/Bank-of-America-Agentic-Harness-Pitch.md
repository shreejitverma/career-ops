---
type: playbook
track: [ai-eng, sde]
level:
status: draft
last_reviewed:
sources: [https://github.com/shreejitverma/agents, https://github.com/shreejitverma/fleet-ops, https://github.com/shreejitverma/dotfiles-nix, https://github.com/shreejitverma/firstmate]
---

# Bank of America final round - tailoring the agentic harness pitch (private)

Private prep for the final round on Thu 2026-09-24: full-stack SWE, Global Markets technology.
Company context lives in [Bank of America](Bank-of-America.md); the public interview pack is [Pitches](../../../13-Agentic-AI/Agentic-Harness/interview/Pitches.md), [JD-Mapping](../../../13-Agentic-AI/Agentic-Harness/interview/JD-Mapping.md), [Question-Bank](../../../13-Agentic-AI/Agentic-Harness/interview/Question-Bank.md), [STAR-Stories](../../../13-Agentic-AI/Agentic-Harness/interview/STAR-Stories.md), and [Cheat-Sheet](../../../13-Agentic-AI/Agentic-Harness/interview/Cheat-Sheet.md).
No personal details about the interviewer are recorded here by design.

## What this role cares about (from the JD)

- Full SDLC and STLC ownership, with unit test coverage.
- Releases that satisfy enterprise and regulatory controls.
- CI/CD with AWS CDK, CloudFormation, and CodeBuild.
- Distributed, reliable pipelines.
- A trading-desktop UI stack: React, ES6+, websockets, OpenFin, Electron, Tailwind.
- Python or Java OO, code quality, and partnering with the business, in Global Markets.

The company note adds that Global Markets technology is regulation-heavy, code must be audit-ready, and teams run Agile inside a large technology organization.

## The likely lens of an engineering manager in markets technology

Assume the questions behind the questions are these, and answer them before they are asked:

1. **Will this person ship reliably without creating release risk?**
   Lead with the gate: one publication path, evidence bound to the commit, human merge authority.
2. **Can they own a desktop trading UI in production?**
   Show Electron security fluency and websocket feed design; be upfront that OpenFin and the frontends in the fleet are not my code.
3. **Will their use of AI create a compliance problem?**
   Show that my harness makes AI use more controlled, not less: approved tools only, no secrets in config, guard on destructive commands, human approval on merges, and an audit trail per change.
4. **Can they work with traders and stakeholders under time pressure?**
   Use intent-first briefs and outcome-language reporting as the pattern; bring a real business story from prior experience.
5. **How fast will they ramp on our stack (AWS pipelines, Java services)?**
   Name the gaps first, then show the control design already maps one to one.

## 90-second pitch tailored to this room

> In my own engineering setup I run AI coding agents the way a markets technology team runs releases.
> A supervisor agent takes my intent, checks capacity limits before dispatching, and runs each task in an isolated workspace.
> Nothing reaches GitHub except through one gate: review, tests, docs, lint, a push of the exact verified commit, and a PR that carries evidence bound to that commit, with merges only on my explicit approval.
> Across 228 changes the gate caught and fixed a mistake in 58 percent of them.
> Most of the tools are open-source forks; my work is the policy, integration, and operations: the routing rules, a guard hook on every shell command, and infrastructure as code that rebuilds and verifies the whole fleet daily.
> For this role, the parts that transfer are release discipline with evidence, testing of code that touches real state, and unattended pipelines that fail loudly.
> The gaps I would close first are AWS CodePipeline with CDK, and OpenFin; I know exactly where each control I built would live in those tools.

## Mapping the harness onto a Global Markets desktop and release process

| Their world | My harness analogue | How to say it |
| --- | --- | --- |
| Change ticket plus approval before prod | Gate attestation plus merge on my word | "The attestation is the automated half of your change record; the approver stays human." |
| Segregation of duties | Supervisor never edits code; worker cannot skip the gate; merge authority is mine | "Doer, checker, and approver are separate by construction." |
| Pre-trade limit checks | Runway gate before dispatch, Tier 1 never downgraded | "Check the limit that binds before you route." |
| Golden-source reference data | Fast-forward-only fork sync, divergence reported not merged | "Consumers never edit the source; divergence becomes a decision." |
| Desktop app security (OpenFin, Electron) | Context isolation and a narrow preload bridge in the Electron apps I run | "Renderer never gets Node; entitlements live behind one audited bridge." |
| Market-data websockets | Coalescing queue and heartbeats in the websocket apps I run | "Sequence-numbered deltas, snapshots, per-instrument conflation, resubscribe on reconnect." |
| Release pipeline on AWS | My gate plus CI plus drift checks | "CDK Pipelines with CodeBuild steps, change sets as evidence, manual approval before prod." |

## OpenFin and Electron talking points (prepare, do not overclaim)

- State the fact first: there is no OpenFin code in anything I run (`git grep -il openfin` returned nothing across the app repos on 2026-09-23).
- What I can speak to from the Electron apps I run and test: `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, and a single typed `contextBridge` API routed to one IPC registry.
- What OpenFin adds on top of a Chromium runtime (from public docs, hedge accordingly): managed window layouts for multi-monitor desks, an inter-application message bus and channels, FDC3 interop between apps from different vendors, and centrally managed runtime versions and app manifests.
- Blotter performance habits to mention: virtualized grids, batching updates per animation frame, conflating ticks per instrument when the UI falls behind, and keeping heavy work off the render thread.

## Regulatory release controls: what to emphasize

- Evidence bound to the exact artifact: the gate pushes a verified SHA and re-reads the remote, and the PR attestation is checked by a required status check.
- Controls cannot be weakened from a branch: the gate reads security settings only from the default branch, and my guard denies unattended edits to existing lint or gate config.
- Honest limit to say out loud: AI review is probabilistic evidence, not a compliance certification; the bank still needs human review, SAST, and the change process.
- What I would add in a bank: ticket linkage in the PR template, a second human approver, retention of gate logs as audit evidence, and dependency and license scanning in CodeBuild.

## Top 10 questions to rehearse aloud tonight

Say each answer out loud once, under 90 seconds, then check it against the source.

1. "Walk me through a system you built end to end." Use the 2-minute pitch and draw the 12 boxes ([Pitches](../../../13-Agentic-AI/Agentic-Harness/interview/Pitches.md)).
2. "How do you ensure release quality and compliance?" Gate, attestation, human merge, default-branch-only settings ([Question-Bank](../../../13-Agentic-AI/Agentic-Harness/interview/Question-Bank.md) Q3, Q27, Q46).
3. "Tell me about a bug you caught before production." Story 1, the guard hook failing open ([STAR-Stories](../../../13-Agentic-AI/Agentic-Harness/interview/STAR-Stories.md)).
4. "Tell me about an incident and how you responded." Story 3, quota exhaustion on 2026-09-18.
5. "How would you build CI/CD on AWS with CDK and CodeBuild?" The six-step bridge in [JD-Mapping](../../../13-Agentic-AI/Agentic-Harness/interview/JD-Mapping.md) section 4.
6. "Design a real-time blotter over websockets." Typed message union, snapshot plus sequence-numbered deltas, conflation, heartbeats, reconnect with resubscribe, virtualized grid.
7. "What is your experience with OpenFin or Electron?" Electron security model first, OpenFin gap stated plainly, then what transfers.
8. "How do you approach unit testing and coverage?" Sandbox the real script, assert state not source, regression test per bug; no coverage metric yet and how I would add it ([Question-Bank](../../../13-Agentic-AI/Agentic-Harness/interview/Question-Bank.md) Q41, Q42, Q44).
9. "How do you use AI tools safely in a regulated environment?" Approved tools only, no secrets in config, guard hook, human approvals, audit trail, prompt-injection stance ([Question-Bank](../../../13-Agentic-AI/Agentic-Harness/interview/Question-Bank.md) Q23 to Q29).
10. "How do you work with traders or business stakeholders?" Intent captured verbatim and verified against, outcomes over mechanics, plus one real story from prior work.

## 60-minute prep plan for tonight

| Time | Block | Output |
| --- | --- | --- |
| 0:00 to 0:10 | Read [Cheat-Sheet](../../../13-Agentic-AI/Agentic-Harness/interview/Cheat-Sheet.md) twice; memorize the 10 numbers and the authorship split | Can say "mine vs upstream" without notes |
| 0:10 to 0:20 | Draw the 12-box whiteboard from memory three times, narrating the 2-minute pitch out loud; time it | Under 2:15 on the third pass |
| 0:20 to 0:32 | Rehearse the three STAR stories aloud using the 60-second versions | Each under 75 seconds |
| 0:32 to 0:44 | Rehearse questions 5, 6, and 7 above: AWS pipeline bridge, blotter design, OpenFin and Electron | One clean sketch each on paper |
| 0:44 to 0:54 | Rapid fire from [Question-Bank](../../../13-Agentic-AI/Agentic-Harness/interview/Question-Bank.md): Q9, Q10, Q12, Q16, Q23, Q34, Q47 | 30-second answers |
| 0:54 to 1:00 | Write three questions to ask them; set out water, pen, and paper for the whiteboard | Ready to stop |

## Questions to ask them

- How are desktop releases for the trading platform gated today, and where does most release friction come from?
- What is the current mix of OpenFin and other desktop technology on the team, and how is market data delivered to the UI?
- How is the team adopting AI coding tools, and what guardrails does the bank require?

## Do not

- Do not claim authorship of firstmate, no-mistakes, treehouse, or the frontend apps.
- Do not quote upstream benchmark numbers as my measurements.
- Do not describe the harness as secure; say it limits blast radius.
- Do not bring up personal repositories that are unrelated to the role unless asked.
