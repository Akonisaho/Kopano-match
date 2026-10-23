# The demo: two stories in 2:30

One idea carries it: **Kopano turns "no" into "here is the fastest way to yes".** Show it twice, once
from each side, then prove it is responsible.

## Setup (once, the evening before)
```
python seed.py --empty
python -m uvicorn app.main:app --port 8000        # with your real Gemini and Brevo keys in backend/.env
python scripts/build_demo.py --email you@yourdomain.co.za
python scripts/make_demo_documents.py "Isizwe Civil Works"      # sample certificates in demo-documents/ (all expire 31 Dec 2027)
```
Sign in once as each account and let the browser remember nothing. Open the phone with the passport
link ready. Keep the in-app bell open: it works even if email is slow.

## 0:00 to 0:20. Hook (landing page)
"A small business loses a R4 million contract and is never told why. Watch." Let the landing page hero
play once: the dot is blocked, two documents are named, then it glides to award ready and R4 200 000 unlocks.

## 0:20 to 1:20. Story one: the business (`demo+isizwe@…`)
1. **Home:** "R4 200 000 is waiting for Isizwe, one step away." Point at the single number.
2. **Unlock Plan:** tick the two documents. "Seven days, fourteen days, R0. The platform tells him exactly what to do."
3. **Documents:** choose the type, pick `COID.pdf`, press upload, then do the same with `CIDB.pdf`. You do not need to type a date. Each file is read on this computer in a blink, the expiry date is filled in from the document, and the checks run. The R4.2m needs both. The reader
   checks it against the account. "It reads the paperwork, he stays in control."
4. **Home again:** scores refresh the moment each file lands. After the second one the number drops and the business is award ready.
5. **Passport:** create it, show the QR, open it on the phone. "One link he can give any buyer, even outside
   this platform. He controls it."

## 1:20 to 2:10. Story two: the buyer (`demo+buyer@…`)
1. **Roads tender:** the chart, then the ranked list. Open one match: two scores, costed gaps, capacity flag.
2. **Meaning check:** one click, advisory, "it never changes the score."
3. **Agri-hub:** "nobody covers it alone", so a three-business consortium covers 100%.
4. **Impact:** "R1.7m went to a business that still had a document gap. A strict filter would have rejected it."
5. **Feedback:** one rating left, one answered. "Reviews are disputable, and a reviewer decides."

## 2:10 to 2:30. Proof and ask
Open **Responsible AI**: "Flip ownership and zero scores change. Same input, same answer, tested. We show
our one fairness gap instead of hiding it." Then the **YES ecosystem** dashboard for five seconds. Close on the ask.

## If something goes wrong
- Gemini slow: the draft says "not available" and nothing is lost. Say so and move on; the rest is rules.
- Email late: point at the bell.
- Anything breaks: the landing page stories and the Responsible AI page work with no sign-in.

## Practising
Reset to the starting point at any time (about a minute):
```
.\scripts\reset-demo.ps1                                          # practice, no real email
.\scripts\reset-demo.ps1 -RealEmail -Email you@yourdomain.co.za   # the recording
```
Three passes, in this order:
1. **Dry run, no timer.** Click through the whole script once. Fix anything that surprises you.
2. **Timed run, out loud.** Aim for 2:30 to 2:45. If you run over, cut the YES dashboard, then the consortium.
3. **Recording takes.** Reset, record, and keep the best take. Reset again for every retake.

Before every take: refresh the page, close the file picker folder you do not need, and silence notifications.

