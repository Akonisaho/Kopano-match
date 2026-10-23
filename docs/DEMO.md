# The demo: one story, told twice, in 2:30

**Kopano turns "no" into "here is the fastest way to yes".** The business unlocks a contract. The buyer
hears about it live, in the same minute. Then we prove it is fair.

Everything runs on this computer: no network, no outside service, nothing to go wrong. Documents are really
read (company, type, expiry, issuer), scores really recalculate, and the buyer really gets the news.

## Setup (once, before you record)
```
.\scripts\reset-demo.ps1
```
That rebuilds the demo in about a minute, opens the sample certificates folder and the app. For the recording
with real email to your own inbox: `.\scripts\reset-demo.ps1 -RealEmail -Email you@yourdomain.co.za`.

Accounts (password `Demo-Password-1!`): business `demo+isizwe@kopano-test.com`, buyer `demo+buyer@kopano-test.com`,
admin `reviewer@kopano-test.com` with `Another-Strong-Pass-9!`. Keep two browser windows open, one for each.

## 0:00 to 0:20. The hook (no account needed)
Landing page. Let the hero play once: a business is blocked, two documents are named, the dot glides to award ready
and R4 200 000 unlocks. *"Small businesses lose contracts over paperwork nobody tells them about. We tell them, and we price it."*

## 0:20 to 0:40. Try before you sign up
Press **Browse open opportunities**. Tap the type chips: *Procurement, Grant, Funding, Investment, Business support*, each with its count. *"Every kind of opportunity in one place."* Open the roads tender. Tick two capabilities and a document in the checker; the verdict
moves as you tick. Open **How the platform decided**. *"Anyone can check their fit before they register. Nothing is stored. We only ask for an account when they want to act."*

## 0:40 to 1:30. The business: unlock (`demo+isizwe@…`)
1. **Home:** *"R4 200 000 is waiting for Isizwe, behind two documents."*
2. **Documents:** pick type **Letter of good standing**, choose `COID.pdf`, press upload. It is read in a blink. Point at what it found, the match with the account, and the expiry date it filled in itself. Press Done.
3. Do the same with **CIDB certificate** and `CIDB.pdf`.
4. **The unlock moment:** the whole screen turns gold: *R4 200 000, award ready, the buyer has been told.* Press **Apply now**.
   *"Seconds, not weeks. And the buyer already knows."*
5. **Home:** "You are award ready." Create the **passport**, open the QR on your phone. *"One link that proves what she can show any buyer, on or off the platform."*

## 1:20 to 1:35. Your language, your voice
On the business home, open the language switcher and choose **Afrikaans**. The whole screen changes, including the
plain-words explanation, and the numbers stay identical. Press **Listen**. *"Her scores never change with her language.
That is the point: how she speaks must not decide whether she wins."* (isiZulu and Sesotho are drafts: keep them for after a
native speaker has checked them, and switch back to English before the buyer story.)

## 1:35 to 2:10. The buyer hears about it (`demo+buyer@…`)
1. Open the bell: **Now award ready: Isizwe Civil Works** and **New application**. *"No chasing, no spreadsheets."*
2. **Roads tender:** the ranked list, Isizwe near the top. Open her match: the two scores, the plain-words summary, the track record.
3. **Impact:** *"R1.7m went to Nomsa Builders while she still had a document gap. A strict filter would have rejected her. We coached her instead."*
4. **Agri-hub:** *"Nobody covers it alone, so we assemble a team of three."*

## 2:10 to 2:30. Proof and ask
Open **Responsible AI**: *"Flip ownership and zero scores change. Same input, same answer, tested. We even show our one fairness gap."*
Ten seconds on the **Ecosystem** dashboard for YES: the **Inclusion** panel shows how many businesses work in a home language, voice use, and that it costs them nothing at award. Close on the ask.

## Practising
Reset (about a minute) before every pass:
```
.\scripts\reset-demo.ps1
```
1. **Dry run, no timer.** Click the whole script once. Fix anything that surprises you.
2. **Timed run, out loud.** Aim for 2:30. If you run over, cut the agri-hub, then the ecosystem dashboard.
3. **Recording takes.** Reset, record, keep the best. Reset again for every retake.

Before every take: refresh, close other windows, silence notifications.

## If something goes wrong
- **Upload does nothing:** reset and try again; the reader needs a PDF with text (the sample certificates have it).
- **A scan or image:** it says honestly that there is no readable text. Show that as a feature: *"it never invents."*
- **Anything breaks:** the landing page and the public opportunities need no account and no data. Start there.
