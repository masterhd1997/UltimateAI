# AI-First Gameplay Editor Design

Date: 2026-06-25
Product: GameCut AI

## Goal

GameCut AI should feel like a simple CapCut-style editor with an AI autopilot for people who want to make videos but do not know how to edit, or find editing overwhelming. The first screen should stay simple: upload gameplay, choose or confirm the kind of content they want, and let the AI create a finished edit that can still be tweaked manually.

The app is for any game or gameplay genre: horror, simulator, FPS, racing, survival, sandbox, tutorial, cinematic, funny, and creator-style formats.

## Product Principle

The default experience is not a professional timeline with hundreds of controls. It is:

1. Upload video.
2. AI watches the full video.
3. AI asks a few simple questions based on what it saw.
4. AI researches similar public content patterns.
5. AI edits the customer video automatically.
6. User can preview, export, or make simple changes.

Advanced editing tools exist, but they are secondary.

## Modes

### AI First

This is the primary product path. The user uploads footage and clicks `AI Edit My Video`. The app analyzes the whole video before rendering. It detects genre signals, highlight moments, pacing opportunities, audio spikes, scene changes, and likely content format.

After analysis, it asks short questions such as:

- "Are you making content for viewers who like creators such as GrayStillPlays, Drae, Markiplier, CoryxKenshin, IGP, or NoahJ456?"
- "Is this meant to be funny, scary, hype, cinematic, tutorial, or auto?"
- "Is this for YouTube, Shorts, TikTok, or a general export?"

The app then creates an edit plan and renders it.

### Manual Editor

Manual controls remain available for trims, cuts, captions, effects, sounds, and export. They should be easy and not overwhelming. This gives users confidence that they can fix small things without needing to understand a full professional editor.

### Creator Assistant

The assistant guides users toward a content style without copying any creator's exact content. It can show creator names as audience/style references, but the app should phrase this as:

- "For viewers who like..."
- "Inspired by high-level pacing patterns common in..."
- "Similar format to..."

It should not claim to copy, impersonate, or reproduce a creator's exact style.

## Research-Driven Editing

The app should research similar YouTube content using the uploaded video's game name, detected genre, chosen style, and user-confirmed creator targets.

The research system may use public search results, metadata, titles, descriptions where available, durations, view counts, upload patterns, and high-level content signals.

The app should not copy other creators' footage, music, thumbnails, memes, or exact edits. The render should use:

- the customer's uploaded video,
- generated captions,
- built-in or licensed sound effects,
- built-in or licensed visual assets,
- high-level edit recipes created by GameCut AI.

## Genre and Creator Recipes

The app should keep reusable edit recipes. Examples:

- FPS/shooter: fast cuts, clutch emphasis, punchy zooms, bass hits, highlight captions.
- Horror: suspense holds, darker grade, reaction zooms, jump-scare timing, static/glitch effects.
- Simulator: progression pacing, satisfying reveals, clean cuts, escalation captions.
- Racing: speed ramps, impact cuts, motion emphasis, finish/lap highlights.
- Funny/sandbox: freeze frames, meme timing, reaction captions, safe sound effects.
- Cinematic/story: longer shots, subtle grade, fades, music-sync pacing.

Creator-style recipes should describe high-level audience expectations, not exact copied edits:

- GrayStillPlays-style simulator chaos: escalation cuts, weird-moment zooms, dry/funny captions.
- Drae-style simulator discovery: curiosity pacing, progression, satisfying reveals.
- Markiplier-style horror audience: suspense holds, reaction emphasis, jump-scare timing.
- CoryxKenshin-style horror/funny audience: reaction moments, energy shifts, comedic timing.
- IGP-style survival/horror audience: atmosphere, exploration, tension, reveal cuts.
- NoahJ456-style Zombies/FPS audience: progression, hype pacing, objective/cutscene emphasis.

## Shared Learning and Accounts

Accounts are required so users do not lose preferences, projects, edit recipes, creator targets, or history if their PC turns off, loses power, or they switch machines.

The first cloud-backed version should save:

- account profile,
- app settings,
- creator targets,
- local project history,
- edit recipes selected or approved by the user,
- unfinished edit plans,
- anonymous feedback signals.

Raw video uploads should stay local by default in the first release. Cloud video backup should exist in the architecture but stay hidden or feature-flagged until Pro.

## Shared Recipe Learning

The app should improve over time from anonymous feedback. It should collect recipe-level signals, not raw customer videos by default.

Examples of safe shared learning:

- "Horror + Markiplier audience + suspense recipe was accepted."
- "Simulator + GrayStillPlays audience + chaotic escalation recipe was exported."
- "FPS + hype montage + fast-cut recipe was rejected."

This shared learning improves default recipes for everyone while reducing privacy and storage risk.

## Rollout and Monetization

The app should launch as a free beta first.

Milestones:

- 250 accounts: validate demand and fix onboarding.
- 500 accounts: add better free recipes, effects, captions, and asset packs.
- 1,000 accounts: prepare Pro infrastructure, pricing, and cloud backup tests.
- 2,000 accounts: launch Pro if users are active and the product is strong enough.

Pro features should stay hidden or feature-flagged until the app is good enough. Candidate Pro features:

- cloud video backup,
- premium effect packs,
- premium licensed sound/assets,
- longer videos,
- faster processing,
- advanced creator packs,
- priority updates.

## Architecture

### Local Desktop App

The desktop app remains responsible for importing video, local analysis, local rendering, preview, export, and dependency checks. It should store local data in `%LOCALAPPDATA%\GameCutAI`.

Local modules:

- video analyzer,
- genre classifier,
- edit planner,
- recipe engine,
- asset selector,
- renderer,
- project store,
- update client,
- dependency manager.

### Cloud Services

Cloud services are needed for accounts and shared learning.

Services:

- authentication,
- user profile/preferences,
- project metadata sync,
- recipe database,
- anonymous feedback ingestion,
- recipe update delivery,
- feature flags,
- account milestone tracking,
- Pro entitlement system later.

Cloud video storage should be designed but not enabled by default until Pro.

## Data Flow

1. User uploads video.
2. App analyzes the full video locally.
3. App classifies genre and likely content format.
4. App searches/researches similar public YouTube patterns.
5. App shows creator/category suggestions to the user.
6. User confirms or changes the target.
7. App chooses an edit recipe.
8. App creates an edit plan with cuts, captions, effects, sounds, images, and overlays.
9. App renders locally using FFmpeg.
10. User previews and exports.
11. App saves project metadata to the user's account.
12. App sends anonymous recipe feedback only if shared learning is enabled.

## Privacy and Safety

The app must be clear about what it sends online.

Default:

- Do not upload raw videos.
- Do not upload personal files.
- Do not copy YouTube videos.
- Do not download creator content for reuse.
- Store account/project metadata and preferences.
- Share anonymous recipe feedback for improving global recipes.

If cloud video backup is enabled later, it must require clear user consent and show storage limits.

## YouTube and Copyright Boundary

The app can use YouTube research for high-level inspiration and trend detection. It must not copy creator footage, audio, thumbnails, exact edits, or proprietary assets.

Allowed:

- search result metadata,
- broad content categories,
- pacing summaries,
- title/topic patterns,
- creator names as audience references,
- high-level recipe suggestions.

Not allowed:

- reusing creator video clips,
- copying exact editing sequences,
- downloading and reusing copyrighted music,
- copying thumbnails or memes without rights,
- claiming the app makes videos exactly like a creator.

## First Implementable Version

The first version should not try to do everything.

Build:

- full-video local analysis,
- auto genre classification,
- creator/category suggestion screen,
- YouTube metadata research,
- recipe-based edit planning,
- built-in safe asset library,
- local render with cuts/captions/effects,
- account sign-in foundation,
- local project history,
- anonymous shared feedback events.

Defer:

- raw video cloud backup,
- paid Pro launch,
- large premium asset marketplace,
- full creator-specific deep model training,
- uploading customer videos for cloud AI analysis.

## Testing

Automated tests should cover:

- genre classification from analysis signals,
- recipe selection from genre and creator target,
- edit plan generation,
- safe asset selection,
- no raw video upload by default,
- account project metadata sync,
- anonymous feedback payload shape,
- update/recipe manifest handling,
- render command generation.

Manual verification should include:

- horror clip,
- simulator clip,
- FPS clip,
- funny/sandbox clip,
- long video,
- short video,
- missing FFmpeg setup,
- account sign-in interrupted by power/network loss,
- update check with and without configured feed.

## Success Criteria

The feature succeeds when a beginner can upload a gameplay recording, answer one or two simple questions, and receive a finished edit that looks intentionally paced for their chosen genre or creator audience.

The user should not need to understand editing terminology to get a useful result.
