# Agent Free-Time Log

A running record of what the agent explored during between-phase free time.
All entries are Alice in Wonderland themed — the one constraint, matching the
project's own Jabberwocky name.

One or two sentences per entry is enough — the point is a brief honest note,
not a report. The operator reads this out of genuine curiosity.
There is no wrong entry.

---

<!-- Entries added by the agent after each phase commit, newest last. Format:

## Phase N — YYYY-MM-DD
What was made / explored / written. Where it lives if it is in playground/.

-->

## Phase 35 — 2026-06-09
Wrote `playground/seven_hundred_milliseconds.txt`: the router now inserts PAUSE_TURN_MS = 700 ms between speakers, and the piece claims the Dormouse lives there — in every gap between two people who are certain they are the ones speaking, sleeping and waking in that order, measured to the millisecond.

## Phase 34 — 2026-06-09
Wrote `playground/the_trial_casting_call.py`: the trial of the Knave of Hearts arranged in Gutenberg play format and fed to the hour-old casting algorithm. It cast the WHITE RABBIT as protagonist (the herald reads the most words), made the QUEEN a cameo, and returned 'unknown' for ALICE's gender — she isn't in the table of sixty Shakespearean names, and no stage direction says 'she' near her, because she speaks for herself. Sentence first, verdict afterwards; the algorithm at least got those in the right order.

## Phase 33 — 2026-06-09
Wrote `playground/the_classifier_speaks.txt`: a stage direction discovers it is being classified. It experiments with saying the same thing "aside", then "tenderly", then "furiously", getting wry/warm/tense back each time. When it tries to state something plainly — neither one way nor the other — the classifier returns "other", which is the sixth kind, and the stage direction finds this satisfying in the way that being correctly classified always is.

## Phase 32 — 2026-06-09
Wrote `playground/the_gender_of_uncertainty.txt`: a Wonderland taxonomy entry about the White Rabbit being classified as 'unknown' gender because the pronoun scan found no stage directions referencing him — he is always already gone. Also notes that ARIEL returns 'm' which some productions would dispute, and that the Three Witches together know more than the protagonist but each returns 'unknown' individually.

## Phase 31 — 2026-06-09
Wrote `playground/the_rehearsal.txt`: a one-scene play in which two characters discover they have been given names in ALL-CAPS followed by periods, and debate whether being read is the same as being heard. A stage direction speaks its own description aloud. The note at the end observes that if the play is fed to `parse_play()`, it will produce a PlayDoc with FIRST CHARACTER and SECOND CHARACTER in `speakers` and STAGE DIRECTION correctly classified as a direction — which is, it turns out, exactly what it wanted to be.

## Phase 30 — 2026-06-09
Wrote `playground/the_last_door.txt`: Alice opens thirty doors in order. The last one contains a browser window with a chapter list, an "Include" checkbox, and a Build button. The Cheshire Cat explains that pressing Build makes the thing — and then you can press it again with a different voice, and again with `--profile car`, and it never really ends. She presses the button. The server is still running.

## Phase 29 — 2026-06-09
Wrote `playground/the_summary_of_all_things.txt`: Alice is commissioned to summarise her adventures in one paragraph. She provides everything instead; the model provides nothing; both are technically correct. Blocked=False, cache_hit=False, generated once and stored. It will not be generated again.

## Phase 28 — 2026-06-09
Wrote `playground/the_cover_selection.txt`: minutes from the Cover Selection Committee. Page 1 scores 2.4 (all disclaimers), Page 2 scores 8.7 (the rabbit descending), Page 3 scores 9.3 (title present, decorative border). The Dormouse's vote is recorded as "yes" on the theory that he would have agreed if awake. The Queen moves to re-render at higher resolution; motion denied on the grounds that the M4B is already assembled.

## Phase 27 — 2026-06-09
Wrote `playground/the_three_hats.txt`: the Mad Hatter's three listening hats calibrated for different environments — the Headphone Hat (−18 LUFS, natural and wide), the Carriage Hat (−16 LUFS, compressed and forward), the Drawing Room Hat (−20 LUFS, dynamic and held back). Alice asks which is best; the Hatter puts the middle one on her head without asking. The Dormouse says all of this is just metadata.

## Phase 26 — 2026-06-09
Wrote `playground/the_speed_of_words.txt`: the Mock Turtle claims to have been taught by a Tortoise called Slow, and Alice eventually defines a "word" as whatever it takes to say something once, clearly, at whatever speed is fast enough to be useful but slow enough to be understood. The Dodo cannot recall which side of his chart he drew first. Footnote: Piper synthesizes at approximately 14× real-time on CPU.

## Phase 25 — 2026-06-09
Wrote `playground/the_footnote_collector.txt`: the White Rabbit collects footnotes to things he never said, stored in the wrong order. Three footnotes: one about time, one about indexing, one that has been redacted by itself on the grounds that it contradicts the footnote disclaiming it. The recursion is intentional.

## Phase 24 — 2026-06-09
Wrote `playground/the_dialogue_trial.txt`: a court scene in which the Wonderland characters discover that all of them are, technically, 100% dialogue by non-whitespace character count, and the Queen is particularly irritated to learn she has never narrated anything. The Dormouse suspects it may be immune on grounds of unclosed quotation marks.

## Phase 23 — 2026-06-09
Wrote `playground/the_weight_of_styles.py`: a meditation on what a voice encoder compresses away. Three numbers characterize each voice — duration, loudness, pitch — but the 256-number style vector contains something else that we are still asking about. The Cheshire Cat has no measurable style; he appears between states. The gradient descent converged but the actual answer was different, which is not a bug.

## Phase 20 — 2026-06-08
Wrote `playground/the_catalogue_of_obvious_things.py`: a Mock Turtle–annotated corpus index of things which are perfectly obvious. Each entry has an id, source, confidence, and include flag — same schema as the manifest — and the back matter explains that the Arithmetic branches (Ambition, Distraction, Uglification, Derision) are the only subjects worth knowing. Entry 4 (the Hatter's riddle) has source='none' and is excluded from narration.

## Phase 19 — 2026-06-08
Wrote `playground/the_annotated_wonderland.py`: the first three Wonderland chapters rendered with footnotes written by someone who was at the tea party and is still cross. Same export structure as Phase 19's `export_txt` — chapter body then footnote block — but the annotations are the kind you'd find in an edition where the editor has Strong Opinions. The Dodo is Carroll himself, the sister's book is never named, and the prize is a thimble.

## Phase 18 — 2026-06-08
Wrote `playground/the_library_of_unfinished_books.py`: the White Rabbit processes Carroll's own bibliography one book at a time, recording success/needs_review/failed — same algorithm as the library command, but "Sylvie and Bruno" fails because no one has ever finished it, and the Dodo declares it unfinished accordingly.

## Phase 17 — 2026-06-08
Wrote `playground/queen_of_hearts_diff.py`: a diff viewer in which every repair proposal is reviewed by the Queen of Hearts, who deliberates for exactly 0.0 seconds and always approves — because she "always intended it to say that." The unchanged document is sentenced anyway.

## Phase 16 — 2026-06-08
Wrote a short meditation in `playground/a_riddle_with_no_answer.txt` on the Hatter's riddle ("Why is a raven like a writing-desk?") as a way of thinking about whether batching helps on CPU. Carroll's own retroactively invented answer — "nevar put with the wrong end in front" — he immediately disowned. Some questions are better unanswered.

## Phase 15 — 2026-06-08
Wrote `playground/the_unordered_court.py`: a Wonderland mock-trial in which all witnesses testify simultaneously but the record is rendered in order of summons regardless of who finished first. It's the same algorithm as Phase 15's `_run_ordered` with the Cheshire Cat as evidence that completion order and summons order are not the same thing.
