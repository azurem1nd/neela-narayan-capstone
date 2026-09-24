# TRACK RECORD — Logic Q&A

> Source of truth for this document: the actual repository as it exists today —
> `session_detection.py`, `track_features.py`, `context_detection.py`,
> `playlist_persistence.py`, `playlist_naming.py`, `spotify_playlist.py`, `app.py`,
> and the corresponding `.claude/skills/*/SKILL.md` files. Every number and rule
> below was read directly from that code, not recalled from memory or assumed.
> Anything that could not be confirmed this way is explicitly marked
> `NEEDS VERIFICATION`. Anything that is a plan/idea rather than working code is
> explicitly marked `PLANNED, NOT IMPLEMENTED`.

---

## 1. Overall System

### What is the overall flow of TRACK RECORD?

```
Spotify listening history
      ↓
Sessions (session_detection.py)
      ↓
Per-track behaviour classification (track_features.py)
      ↓
Sessions inherit a context label from their tracks (context_detection.py)
      ↓
Qualifying tracks selected for that context
      ↓
Click a card → playlist resolver decides create/reuse/update (playlist_persistence.py)
      ↓
Real Spotify playlist
      ↓
Playlist detail page (re-reads the playlist live from Spotify)
```

Two things worth saying plainly up front, because they change how you should
describe the system:

1. **Classification happens per *track*, not per session, first.** The system
   looks at *every* play of a track across the whole fetch (up to 300 recent
   plays) and decides what kind of listening habit that track shows — before it
   ever looks at sessions. Sessions only come into it afterwards, to decide
   *which* of a track's classifications gets shown on a card.
2. **Nothing is created automatically.** Looking at your library (`/analyze`)
   never creates a Spotify playlist. A playlist is only created, reused, or
   updated when you click a specific card.

### What happens from the moment Spotify data enters the system until a playlist is created?

1. **Fetch.** When you open your library, the app calls Spotify's "recently
   played" endpoint, paging through it until it has collected up to **300**
   plays (or runs out of history). This happens live, every time — nothing is
   stored between visits.
2. **Group into sessions.** Those plays are sorted by time and split into
   listening sessions using a simple gap rule (see Section 2).
3. **Classify every track.** Independently of sessions, every distinct track in
   that 300-play fetch is looked at across *all* its plays in the fetch and
   given a behavioural label: Spiral, Trigger, Companion, or "not enough data
   yet" (see Section 3).
4. **Turn each session into a context.** Each session looks at what its own
   member tracks were classified as, and decides on one label for the whole
   session — either one of the track-level labels (if one clearly dominates),
   or a session-level fallback (Locked / Exploration / Glimpse) if nothing
   dominates (see Section 4).
5. **Show cards.** `/analyze` renders one card per resulting context (contexts
   sharing the same label are merged into one card). At this point, nothing has
   been sent to Spotify — this is just showing you what the system found.
6. **You click a card.** This is the only moment a Spotify playlist is
   involved. The app decides whether to create a brand-new playlist, reuse an
   existing one, or update an existing one's tracks (see Section 5).
7. **Playlist page.** You land on a page that reads the playlist straight from
   Spotify (not from any local copy) and lets you play it in the browser.

---

## 2. Session Detection

### What is a listening session?

A session is a run of plays that are close enough together in time to count as
"one sitting" of listening. It is a purely time-based grouping — it does not
care what the tracks are, only when they were played.

### How does TRACK RECORD decide when one session ends and another begins?

The actual rule, from `session_detection.py`:

- Plays are sorted chronologically.
- The gap between one play and the next is measured.
- If that gap is **strictly greater than 30 minutes**, a new session starts.
  A gap of *exactly* 30:00 does **not** start a new session — the boundary is
  `>`, not `>=`.
- A single play, with nothing before or after it within 30 minutes, is still a
  valid session on its own — it is never merged into a neighbour or discarded.

### How long does it take for a session to be detected?

These are four different questions that are easy to blur together:

| Question | Answer |
|---|---|
| How much listening history does the app look at? | Up to the 300 most recent plays, fetched fresh every time you visit `/analyze`. |
| What decides where one session ends and the next begins? | The 30-minute gap rule above — applied instantly, in memory, once the plays are fetched. |
| When does `/analyze` actually show you the sessions/contexts? | Immediately, as part of rendering the page — there is no waiting period or background job. |
| When does a Spotify playlist get created? | Only when you click a card — never automatically, and never on a timer. |

**Do not describe this as "TRACK RECORD automatically creates a playlist after
30 minutes."** The 30-minute number is only about where a session *boundary*
falls when grouping past plays that already happened — it has nothing to do
with waiting, and it never triggers a playlist on its own.

### Why do we detect sessions before detecting contexts?

Because a context is a property of a *listening occasion*, not of a track in
isolation. Two very different questions are being asked:

- "What kind of habit does this track show, overall?" (track-level — Section 3)
- "What was *this particular sitting* of listening actually like?"
  (session-level — Section 4)

Sessions give the system a sensible unit for the second question. Without
them, the app could only ever say things about individual tracks, never about
"what you were doing on Tuesday evening." Grouping by time first is also what
makes the diversity-based fallback categories (Locked/Exploration) possible at
all — you can't measure "how many different artists were in this sitting"
without first knowing what "this sitting" was.

---

## 3. Track Classification

This step (`track_features.py::classify_track`) looks at *one track* and *all*
of its plays within the current 300-play fetch (not just the plays inside one
session), and returns exactly one of: `Spiral`, `Trigger`, `Companion`, or
`insufficient_data`.

### How does the system identify a Spiral?

A track is Spiral if it was played **3 or more times on the same calendar
date** at any point in the fetch (`density_plays_per_day_busiest_window >= 3`).
In plain English: you binged it hard on at least one day.

### How is Trigger different from Spiral?

| | Spiral | Trigger |
|---|---|---|
| Rule | 3+ plays on one calendar date | Played 2+ times total, and all of those plays fall within a 12-hour span (`active_days < 0.5`) |
| Feel | An intense binge on a single day | A song you reached for a couple of times, but only around one moment — never came back to it later |
| Precedence | Checked **first** | Checked only if Spiral doesn't match |

A track can technically satisfy both conditions at once (a same-day binge is
almost always also "within a 12-hour span"). When that happens, **Spiral wins**
— see below for why.

### How is Companion different from Trigger?

Both require the track to have been played **2 or more times**. The only
difference is the *spread* of those plays:

- **Trigger**: first play and last play are less than 12 hours apart
  (`active_days < 0.5`) — it lived in one moment, then you moved on.
- **Companion**: first play and last play are 12 hours or more apart
  (`active_days >= 0.5`) — you came back to it on a different day, so it
  stuck around.

`active_days` is simply `(last play time − first play time)` converted to
days. The 0.5-day cutoff is what separates "same sitting/day" from "returned
to it later."

### Why does Spiral get checked first?

Because Spiral is the more specific, more intense signal. If a track was
played 3+ times in one day, it will almost always *also* pass Trigger's
"all plays within 12 hours" test — the two conditions overlap. Checking Spiral
first means an intense same-day binge gets called what it actually is (Spiral)
rather than being flattened into the more generic "played a couple of times
that day" bucket (Trigger). The order is a deliberate precedence rule, not
incidental — a documented real example ("One Of Your Girls") satisfies both
conditions and is classified Spiral specifically because of this ordering.

### `insufficient_data`

If a track was played **only once** in the fetch (`play_count < 2`), it gets
the label `insufficient_data`. This is checked first, before any of the other
three rules, and is a real value the system returns today — not a hypothetical
case.

---

## 4. Session / Cluster Logic

### How does a session become a context?

Take a session's distinct tracks (repeats within the session collapse to one
entry), look up each one's track-level classification from Section 3, and find
whichever qualifying label (Spiral/Trigger/Companion) is most common among
them. If that most-common label covers a big enough share of the session's
distinct tracks (see next question), the *whole session* inherits that label.
If nothing dominates strongly enough, the session falls back to a
session-native label instead (Locked/Exploration/Glimpse — see below).

### Why is the 15% representation threshold used?

The constant is `MIN_REPRESENTATION_RATIO = 0.15`, in `context_detection.py`.

- **What's being counted:** the number of a session's *distinct* tracks that
  share the plurality-winning qualifying label, divided by the session's total
  distinct track count.
- **What 15% represents:** the minimum share that winning label must cover
  before the session is allowed to take its name from it.
- **Why it exists:** without a floor, a session with (say) 1 Trigger track out
  of 22 completely unrelated distinct tracks would still get labelled
  "Trigger" purely because nothing else in the session happened to qualify for
  anything — one track with no real competition, not because Trigger actually
  describes that session. The 15% floor stops one thin, unrepresentative
  signal from defining an entire session.
- The exact value (0.15) was chosen by testing it against real recorded
  sessions and confirming it was the smallest threshold that filtered out two
  observed thin-signal cases (a session where the winner covered only 4.8% of
  distinct tracks, and one where it covered 12.0%) — 20% and 25% were also
  tried and gave identical results on that data, so 15% is the least
  aggressive value the evidence actually supports.

### What happens when there isn't enough evidence?

If no qualifying label reaches the 15% floor, the session doesn't just get
discarded — it falls through to a session-native fallback based on the
session's own shape (how many different artists vs. tracks it contains), which
is Locked or Exploration. Only if the session is *too small even for that*
(fewer than 2 distinct tracks) does it fall all the way to Glimpse. So there
are really three tiers, not two: dominant label → diversity fallback → Glimpse.

### How does Locked differ from Explore?

(Internally the category is called `Exploration`; the card the user sees is
titled **EXPLORE** — same category, different display text.)

Both are computed the same way, only for sessions where no track-level label
dominated:

```
ratio = distinct_artist_count / distinct_track_count
ratio < 0.5   →  Locked        (concentrated — few artists relative to tracks)
ratio >= 0.5  →  Exploration   (broad — many different artists relative to tracks)
```

| | Locked | Exploration (EXPLORE) |
|---|---|---|
| Artist-to-track ratio | Below 0.5 | 0.5 or above |
| Feel | A familiar, repeating loop of a small set of artists | Wide-ranging, discovery-style listening |
| Minimum size to qualify | 2+ distinct tracks (`MIN_DISTINCT_TRACKS_FOR_EVIDENCE`) | same |

This ratio-based rule is only reached when no Spiral/Trigger/Companion track
won the session outright — it's a fallback specifically for "no individual
track stood out, but the session's own shape still tells you something."

### When does a session become Glimpse?

Glimpse is the bottom tier: it fires when a session has **fewer than 2
distinct tracks** (`MIN_DISTINCT_TRACKS_FOR_EVIDENCE = 2`) and no track
dominated. In practice this means: the session boils down to a single track,
and that track itself was only played once anywhere in the whole fetch — there
simply isn't enough repetition anywhere to say anything more specific. This
matches the description shown on the card: *"A fleeting listen, with too
little repetition to reveal a pattern."*

---

## 5. Playlist Logic

### Which tracks actually go into a playlist?

Every context carries a field called `playlist_track_ids`, computed once in
`context_detection.py` and used, unedited, for whatever playlist gets
created/updated from it:

- For **Spiral / Trigger / Companion** contexts: only the tracks whose own
  individual classification actually matches the winning label — not every
  track that happened to be in that session.
- For **Locked / Exploration / Glimpse** contexts: the whole session's
  distinct tracks (there's no per-track "qualifies" concept for these — the
  session's shape *is* the evidence).

### Why aren't all session tracks included?

Because a session and a "context" aren't the same thing. A session might
contain a Trigger track sitting next to several unrelated ones that don't fit
that pattern at all. Including everything the user happened to hear in that
window would misrepresent the pattern being highlighted. The displayed track
count on every card is always exactly `len(playlist_track_ids)` — the same
number that gets sent to Spotify, by construction, so the card can never show
a different count than the playlist actually contains.

### When is a Spotify playlist actually created?

**Only from a card click — never from `/analyze`.** Loading your library page
only fetches, classifies, and displays; it never talks to Spotify's
playlist-creation endpoint. The moment a real playlist gets created, reused,
or updated is a `POST /create-playlist` request, sent by the browser when a
context card is clicked.

### Why isn't a playlist created every time I click a card?

Because of `playlist_persistence.py`, added specifically to stop this. Every
click re-fetches your current listening data, recomputes the context, and then
asks a resolver — `resolve_context_playlist()` — what to do, rather than
calling "create" unconditionally:

1. No saved playlist exists yet for this (you, this category) → **create** one.
2. A saved playlist exists and the track set is basically unchanged → **reuse**
   it (no Spotify write happens at all).
3. A saved playlist exists but the track set has meaningfully changed →
   **update** that same playlist's tracks in place.
4. A saved playlist exists but Spotify says it's gone (you deleted it) →
   **create** a replacement.

### How does the system know that I already have a playlist for this context?

It keeps a small local database (`track_record.db`, one row per
user+category) recording the Spotify playlist ID/URL it created last time,
plus a fingerprint of which tracks were in it. Every click looks up that row
by `(your Spotify user ID, the category name — e.g. "Exploration")` before
deciding what to do. The lookup key is always the *real* Spotify user ID
(`sp.current_user()["id"]`), obtained fresh from your session each time — never
a name or session cookie value.

### What happens if the listening pattern changes?

This is implemented, not just planned. The system builds a fingerprint of the
qualifying track set (a hash of the sorted, de-duplicated track IDs — so
reordering or repeats never change it) and compares your *current* track set
against the one saved from last time, using a symmetric "how different are
these two sets" measure (the Jaccard distance: the proportion of tracks that
differ, out of all tracks either set has).

- **Small change** → treated as the same pattern → **reuse**, untouched.
- **Big enough change** → the existing playlist's tracks are **replaced**
  (`sp.playlist_replace_items`) — same playlist ID and URL as before, just
  updated contents. The playlist's **name and description are deliberately
  left as they were originally created** — only the track list changes.

### When does the system reuse vs update a playlist?

The exact, currently-implemented cutoff is:

```
change_ratio = (tracks that differ) / (tracks in either set)
change_ratio <  0.30   →  reuse (no Spotify write)
change_ratio >= 0.30   →  update (tracks replaced)
```

`0.30` is `PLAYLIST_PATTERN_CHANGE_THRESHOLD` in `playlist_persistence.py` — a
real, live constant, not a proposal. It's documented as a reasonable starting
point calibrated against the scale of real session data available at the time
it was written, not something derived from a large dataset — so treat it as
"currently how the app behaves," while being aware it's flagged in the code
itself as open to revision later.

---

## 6. Multi-user Logic

### How does TRACK RECORD know whose listening history it is?

Through Spotify's own OAuth login. When you log in, Spotify hands the app an
access token tied to your account; that token is cached server-side (in the
Flask session store, not a browser cookie) and is what every subsequent
request — fetching plays, classifying, creating playlists — is made with.
There is no separate TRACK RECORD account system; your identity *is* your
Spotify login.

### How are two users' playlists kept separate?

Two ways, both load-bearing:

1. **Spotify itself** already scopes every API call to whichever account's
   token made the request — one user's session simply cannot fetch or modify
   another user's data.
2. **The persistence table is keyed on the real Spotify user ID plus the
   category name** (`(user_id, context)`), so `user_A + "Exploration"` and
   `user_B + "Exploration"` are two entirely separate rows that can never
   collide or be returned to the wrong person.

---

## 7. Edge Cases

### What happens when there isn't enough listening history?

The system doesn't fail — it just produces smaller/emptier results. A session
with too few distinct tracks (or a track played only once) naturally lands in
Glimpse rather than a stronger category; there's no special-cased "not enough
history" error path beyond that.

### What happens if Spotify returns an error?

`/playlist/<id>` catches a failed/not-found lookup and redirects back to the
library rather than showing a broken page. The playlist-creation path
(`/create-playlist`) wraps its work in error handling that logs the real
exception server-side and returns a clear error to the browser rather than
silently failing or creating something wrong. `NEEDS VERIFICATION`: the exact
current wording/status code returned to the browser in every individual
failure branch was not re-verified line-by-line for this document.

### What happens if an existing playlist is deleted?

Handled explicitly: the resolver checks whether the saved playlist ID still
exists on Spotify before trying to reuse or update it. If it's gone, the
system treats it exactly like "no saved playlist" and creates a fresh
replacement, then updates the saved record to point at the new one.

### What happens when a user has no qualifying tracks?

If a context somehow has zero tracks to work with, `resolve_context_playlist`
refuses to create an empty playlist and returns an error action instead — the
app is written not to invent an empty Spotify playlist just to have something
to show.

---

## 8. Important Numbers & Rules

| Value | Controls |
|---|---|
| **300** (`max_plays`) | The most recent plays fetched from Spotify per visit/click — the cap on how much history the whole system ever looks at at once. |
| **30 minutes** (`GAP_MINUTES`, strictly `>`) | The gap between two plays that starts a new listening session. |
| **2** (`MIN_DISTINCT_TRACKS_FOR_EVIDENCE`) | The minimum number of distinct tracks a session needs to reach the Locked/Exploration fallback instead of dropping to Glimpse. |
| **0.15 / 15%** (`MIN_REPRESENTATION_RATIO`) | The minimum share of a session's distinct tracks a plurality-winning label must cover before the session takes that label. |
| **3 plays / 1 day** | Spiral's threshold — 3 or more plays of a track on one calendar date. |
| **play_count ≥ 2 and active_days < 0.5 (12 hrs)** | Trigger's threshold. |
| **play_count ≥ 2 and active_days ≥ 0.5 (12 hrs)** | Companion's threshold. |
| **distinct_artist_count / distinct_track_count, cutoff 0.5** | Locked (below 0.5) vs. Exploration/EXPLORE (0.5 and above). |
| **play_count < 2** | `insufficient_data` at the track level (played only once). |
| **0.30 / 30%** (`PLAYLIST_PATTERN_CHANGE_THRESHOLD`) | The cutoff between reusing an existing playlist untouched and updating its tracks in place. **This is implemented**, not proposed. |
| **30-second playback** | **NOT IMPLEMENTED.** Confirmed by searching the whole codebase — there is no 30-second preview timer or limit anywhere. Playback uses Spotify's Web Playback SDK, which plays full tracks through a real Spotify Connect device, not short previews. Do not describe this as part of the current system. |

---

## 9. One-Minute Explanation

> "TRACK RECORD works by taking your recent Spotify listening history and
> grouping it into sessions — runs of plays with no gap longer than 30
> minutes between them. Independently, it looks at every track you've played
> and works out a behavioural pattern for it: Spiral if you binged it hard in
> one day, Trigger if you played it a couple of times but only around one
> moment, or Companion if you kept coming back to it on different days. Each
> session then inherits whichever of those patterns clearly dominates its
> tracks; if nothing dominates, the session instead gets labelled by its own
> shape — Locked if it stuck to a small, familiar set of artists, Exploration
> if it ranged widely, or Glimpse if it's really just one track heard once.
> Nothing gets sent to Spotify at this point — it's purely showing you what it
> found. Only when you click a card does the app create a real Spotify
> playlist from that context's exact qualifying tracks — and if you click the
> same card again later, it reuses or updates that same playlist instead of
> making a new one, depending on how much your listening pattern has actually
> changed since."

---

*This document reflects the implementation as of the date it was generated.
If any of the source files listed at the top change afterward, re-verify the
relevant section before relying on it again.*
