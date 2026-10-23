# Languages, voice and inclusion

The thesis: **how a business communicates must never decide whether it wins.** Qualified people are excluded
when the platform asks them to write polished English, fill long forms, or read paperwork they cannot follow.
Kopano Match removes three barriers and measures whether it worked.

| Barrier | What we do | Where |
|---|---|---|
| **Language** | The interface, the explanations and the public checker work in English, Afrikaans, isiZulu and Sesotho | the switcher in every header |
| **Literacy and digital skill** | One next step, structured picks instead of writing, read-aloud, voice search, and a support programme that can sign a business up (with consent) | business home, search boxes, the support home |
| **Form of evidence** | The document reader pulls the company, type, expiry and issuer from a certificate; a scan with no text is reported honestly | Documents |

## The guarantee that makes it credible
The scores read **only structured inputs**: sector, province, turnover, years trading, largest past contract,
capabilities, ownership and document status for a business; value, scope, requirements and terms for an
opportunity. There is **no free text and no language** among them. So how a business writes, speaks or which
language it uses cannot change a score. This is shown live on `/responsible-ai` (computed from the engine's own
input types) and tested (`test_language_is_a_preference_that_never_changes_a_score`,
`test_the_engine_reads_no_free_text_and_says_which_inputs_it_does_read`).

## Translation
- **Our own sentences are templates.** The match explanation is built from fixed sentences (`backend/app/i18n.py`),
  so it translates exactly with no AI involved, and the numbers inside never change.
- **Screens use a phrase table** (`frontend/src/i18n-dict.ts`). The English sentence is the key, a missing row falls
  back to English, and `npm run i18n` (also in CI) fails when a page asks for a phrase with no row.
- **Free text is never auto-translated into a decision.** A tender or description may be machine-translated on request
  in future, labelled as such, and it never affects a score.

## Review status. Read this before showing it in public
| Language | Status |
|---|---|
| English | Source |
| Afrikaans | Reviewed |
| **isiZulu** | **Draft. A first-language speaker must check every phrase.** Shown as "beta" in the switcher and on the YES dashboard |
| **Sesotho** | **Draft. A first-language speaker must check every phrase.** Shown as "beta" |

A wrong phrase in front of investors or businesses does harm. Until a native speaker signs a language off, keep
the "beta" label, and prefer English or Afrikaans for anything that is recorded.

## Voice
- **Read aloud** uses a voice already installed on the device. If the device has no voice for the chosen language,
  the button is disabled and says so; it never reads isiZulu with an English voice.
- **Voice search** uses the browser's speech recognition. In Chrome the audio is sent to Google to be turned into
  text, and the button says so. Only the fact that voice was used is recorded (`voice_used`), never audio or words.
- Both are hidden where the browser cannot do them.

## Assisted sign-up
A support programme (the `support` role) can sign a business up from its home page. The programme attests that the
business agreed to the privacy notice, the business gets an email to **choose its own password**, and the officer
never holds its credentials. The audit log records `assisted_signup`. In development only, the link is also shown
on screen so the flow can be demonstrated without an inbox.

## Measuring inclusion (YES dashboard)
The **Inclusion** panel shows, from the platform's own data: the share of businesses working in a home language,
voice use, assisted sign-ups, and by language the number of businesses, profile completion, applications and awards.
The question it answers: *does working in your own language cost a business anything at the point of application
or award?* With demo data it shows the shape, not a result. Real conclusions need real businesses.

## Honest limits
- isiZulu and Sesotho are unreviewed drafts. Voice recognition availability varies by language, browser and device.
- Document reading handles PDFs with real text; Afrikaans or isiZulu certificates need keyword support added to the
  local reader, or a hosted reader.
- Metrics are only as good as the data. Fewer than a few dozen businesses will not show a meaningful gap.
