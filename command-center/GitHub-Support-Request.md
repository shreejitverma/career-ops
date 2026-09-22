# GitHub Support request: purge rewritten history (draft)

Submit at https://support.github.com/contact (topic: "Remove sensitive or private data" / "Removing sensitive data from a repository").
Send it from the account that owns the repository.

---

**Subject:** Please purge cached views and orphaned commits after a history rewrite (sensitive data and third-party copyrighted files)

**Repository:** https://github.com/shreejitverma/SDE-Interview-Prep (public)

Hello,

I removed sensitive data from this public repository by rewriting its history with `git filter-repo` and force-pushing every branch.
The data included scraped recruiter emails, third-party names and phone numbers, contract rates, and job application status (first committed 2026-09-18), plus a personal receipt PDF.
In a second rewrite I also removed third-party copyrighted PDFs (books and paid course material) that should never have been published.

All branches now point at the rewritten history, but the old commits are still reachable on GitHub:

1. By SHA through the web UI and API (cached views).
2. Through pull request refs, in particular `refs/pull/61/head` (PR #61, closed, head `6e38c67196385f9fa5214ea7e8fc1d86b8823069`), which was created after the sensitive data was committed.
3. Possibly through older pull request refs (#1 to #60), which reference commits containing the copyrighted PDFs.

I checked a full mirror after both rewrites: no branch reaches the private data; `refs/pull/61/head` is the only ref that still does.

Commits on the old `main` that contain the private data (tree or diff):

- `23c81e3adeb685707c79d94b1c76fa1437aa45f9` (2026-09-18, first commit with the data)
- `3d54da51322506dc6c280d26fd4fb4c26159244c`
- `febf36b339e7593956eb213c3acc5f71d3393d92`
- `c6bb7e84bd3052a1d8feda8c6280f433e19bcdcf`
- `580cfeb6cbe09784055ed803961a0b8580f1675d` (old `main` head before the first rewrite)

Old `main` head before the second rewrite (the PDF purge): `ded18b6f1d67c78d41c03fff8d0342c88d0b77ef` (2026-09-21).
Every commit reachable from it still contains the third-party PDFs.

Could you please:

- remove the cached views of these commits,
- dereference or delete the affected pull request refs (at least `refs/pull/61/head`) or otherwise make those commits unreachable,
- run garbage collection so the orphaned objects are removed from the repository and its fork network?

No fork of this repository was pushed after 2026-08-22, so no fork contains the private data; forks may still contain the older copyrighted PDFs, which I understand you cannot remove from other users' forks.

Thank you.
