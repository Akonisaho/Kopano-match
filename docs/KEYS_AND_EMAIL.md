# Keys and email, step by step

Both are optional and take about 10 minutes together. Menu names below are from memory and may
differ slightly on the day. If a page has moved, search for the name in quotes.

Your keys go in **`backend/.env`** (create it with `Copy-Item .env.example backend\.env`). That
file is git-ignored. Never paste a key into chat, a ticket or a commit.

## Gemini (AI summaries and drafting)

1. Open **Google AI Studio**: https://aistudio.google.com/apikey and sign in with a Google account.
2. Choose **Create API key**. If it asks for a Google Cloud project, pick the default one or create one.
3. Copy the key (it starts with `AIza`).
4. In `backend/.env` add, with no quotes or spaces:
   ```
   GEMINI_API_KEY=AIza...your key...
   GEMINI_MODEL=gemini-2.0-flash
   ```
   If the check below says the model was not found, replace `GEMINI_MODEL` with a current model name from AI Studio.
5. Check it: `cd backend` then `python scripts/check_keys.py`.

What it changes: each match summary reads "AI-written from the figures", and the profile and
tender "draft from text" helpers work. The prompt carries figures only, with no names or
identifiers. Scores are never set by the model. The free tier has rate limits; if you hit one the
app silently falls back to its template summary.

## Brevo (real emails)

1. Create an account at https://www.brevo.com.
2. **Add a sender.** Open **Senders, Domains and Dedicated IPs**, then **Senders**, then **Add a sender**.
   Use an address you can open. Brevo emails you a verification link: click it.
3. **Create an API key.** Open your account menu (top right), then **SMTP and API**, then the
   **API Keys** tab, then **Generate a new API key**. Copy it once; it is not shown again.
4. In `backend/.env` add:
   ```
   EMAIL_PROVIDER=brevo
   BREVO_API_KEY=xkeysib-...your key...
   EMAIL_FROM=the-address-you-verified@yourdomain.co.za
   EMAIL_FROM_NAME=Kopano Match
   APP_URL=http://localhost:5173
   ```
   `EMAIL_FROM` must be exactly the verified sender.
5. Check it and send yourself a real test email:
   ```
   cd backend
   python scripts/check_keys.py --send-test you@gmail.com
   ```
6. Restart the API so it reads the new values.

Notes:
- A Gmail or Outlook address works as a sender for a demo, but mail from it often lands in spam.
  A sender on your own authenticated domain (SPF and DKIM set up in Brevo) is far better.
- Check Brevo's current free-plan daily limit before a live demo.
- Brevo acts as an operator of personal information. Sign an operator agreement before any real use.
- Register demo accounts with inboxes you own, for example `you+sme1@gmail.com`. Do not use other people's addresses.

## The MFA encryption key (only outside local development)

Locally, two-step sign-in secrets are encrypted with a key derived automatically. For any shared
or hosted environment set `ENVIRONMENT=production` and a real key, and the app refuses to start
without it:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the output in `MFA_ENCRYPTION_KEY=` and keep a safe copy. If the key is lost, users must set
up two-step sign-in again. Also set a long random `JWT_SECRET` (32 or more characters).

## When something is off

Run `python scripts/check_keys.py`. It reports Gemini, Brevo and the sender separately, and says
what to do:

| Message | Meaning |
|---|---|
| Gemini FAIL 400 | The key is malformed or not valid. Create a new one |
| Gemini FAIL 404 | The model name is wrong. Change `GEMINI_MODEL` |
| Gemini FAIL 429 | Out of quota or rate-limited. Wait, or check the plan |
| Email FAIL 401 | The Brevo API key is not valid |
| Sender FAIL | `EMAIL_FROM` is not a verified sender. Verify it in Brevo |
