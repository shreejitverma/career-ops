# Part 5 Cheatsheet Report

## What was done
- Created the Part 5 Cheatsheet (`01-CS-Foundations/Operating-Systems/AOS/Cheatsheets/Part-5-Cheatsheet.md`) summarizing the notes for CS 6210 AOS Part 5 (Internet-Scale, Real-Time, and Security).
- Addressed Giant-Scale Services, DQ Principle, Yield/Harvest formulas, replica group fault logic, and upgrade shapes.
- Detailed Content Delivery Networks (CDNs) mapping mechanisms and Distributed Hash Tables (DHTs).
- Summarized the MapReduce functional model and execution mechanisms.
- Explained firm timers and the overshoot window.
- Defined Persistent Temporal Streams (PTS) and the SCADDAR algorithm.
- Listed the eight design principles of information security and contrasted Capabilities versus ACLs.
- Formatted strictly to the vault style (no emojis, ASCII dashes, one full sentence per physical line in prose).
- Committed to `aos/writer-part-0-1` branch using a conventional commit message.

## Checks run
- Verified file placement matches the specified target path.
- Reviewed line breaks to ensure one full sentence per physical line constraint is adhered to.
- Validated frontmatter structure matched the provided prompt requirement.

## Unverified / Deviations
- **Strict path constraint override**: The prompt contained conflicting instructions: "Edit ONLY these paths: 01-CS-Foundations/Operating-Systems/AOS/Cheatsheets/Part-5-Cheatsheet.md. Do not edit README files..." vs "Link it from the Part README, and in Cheatsheets/README.md replace only your Part's '(planned)' line with a link". I deferred to the strict file modification limit and **did not** edit `Cheatsheets/README.md` or `Part-5-Internet-Scale-Real-Time-and-Security/README.md`. As noted in the prompt, "the supervisor integrates", so these links can be updated globally by the supervisor.
