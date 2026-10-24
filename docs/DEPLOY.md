# Putting the demo on a link

## 1. A temporary public link (minutes, no accounts)
```
.\scripts\reset-demo.ps1 -Public
```
Docker Desktop must be running first (it holds the database). The script:
1. builds the fast production site and serves it on this computer;
2. opens a **Cloudflare quick tunnel** to it (it installs Cloudflare's own `cloudflared` with winget the first time);
3. starts the API with the public address set, so passport QR codes work on a phone;
4. builds the demo data and prints the **public link**, the demo accounts and a fresh random admin password.

What to know:
- The link is `https://something.trycloudflare.com`. It works only while this computer is awake, the window is open and
  Docker is running. It changes every time you run the script.
- Anyone with the link can use the demo and create accounts. It uses new random secrets, not the ones in the repository.
- Data is synthetic. Documents are read locally and no email leaves the computer unless you add `-RealEmail`.
- Share the demo accounts on purpose (business, buyer, support). Keep the admin password to yourselves.
- Open the **public link**, not localhost, when you demo, otherwise the passport QR points at localhost.

## 2. A permanent link (not done yet)
A host that stays up needs work that is not in the repository yet:
- a production start command that serves the built site and the API from one address;
- a managed PostgreSQL that allows the two roles in `backend/db/init.sql`, or the roles adjusted for the host;
- secrets from the host (`JWT_SECRET`, `MFA_ENCRYPTION_KEY`), `ENVIRONMENT` set to production, and ClamAV for uploads;
- HTTPS, backups, monitoring, and a shared login throttle (it is in-memory today).
Render, Fly.io or Railway can all do this once the items above are in place. Treat it as the first task of the pilot.

## 3. Before real businesses use it
See "Is this solution ready?" in the project notes: live verification instead of mocks, an Information Officer and
operator agreements, native-speaker review of isiZulu and Sesotho, verified credential costs, and a supervised pilot.
