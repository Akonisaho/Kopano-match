import { Link } from 'react-router-dom'
import { Logo } from '../ui'

export default function Privacy() {
  return (
    <>
      <header className="topbar"><Link to="/"><Logo /></Link><div className="top-actions"><Link className="btn btn-outline" to="/">Back</Link></div></header>
      <article style={{ maxWidth: 760, margin: '0 auto', padding: '48px 22px', fontSize: 14, lineHeight: 1.75 }}>
        <h1 style={{ font: '800 32px Manrope', marginBottom: 8 }}>Privacy notice</h1>
        <p>Kopano Match matches small businesses to opportunities. This is the short version of what we do with your information.</p>
        <h2 style={{ fontSize: 17, marginTop: 28 }}>What we collect, and why</h2>
        <ul>
          <li><b>Account details</b> (name, email, phone): to run your account. Platform reviewers can see them.</li>
          <li><b>Business profile</b> (sector, province, turnover, years trading, ownership): to score fit. Providers see it only through a match, and only while "visible to providers" is on. Ownership details are used only to match a provider's stated transformation goal and are not shown in the directory.</li>
          <li><b>Compliance documents</b>: to check readiness. Only your organisation and platform reviewers can open them. We keep a fingerprint (hash) to detect the same document reused by another business.</li>
          <li><b>Service emails</b>: a welcome, a shortlisting notice and an application notice go to the people the event concerns, through an email provider that acts as our operator. They carry no scores or documents.</li>
          <li><b>Verification outcomes</b>: a result, a confidence figure and its source. We do <b>not</b> keep selfies, identity images or full ID numbers. The identity check receives the image, returns an outcome, and the image is discarded. We do not store the ID number at all.</li>
        </ul>
        <h2 style={{ fontSize: 17, marginTop: 28 }}>How decisions are made</h2>
        <p>Scores come from fixed rules that you can see on every match. An AI model may help read pasted text and write a plain-language summary, using only figures already on the page. It never sets a score or approves anyone. A human reviews flagged items and makes the final decision.</p>
        <h2 style={{ fontSize: 17, marginTop: 28 }}>Your rights</h2>
        <p>From your Security page you can download everything we hold about you as a file, and delete your account. Deleting anonymises your personal details and removes the files you uploaded. The log of actions is kept, without your name, so that decisions stay accountable.</p>
        <h2 style={{ fontSize: 17, marginTop: 28 }}>Information Officer</h2>
        <p>An Information Officer has not yet been appointed for this pilot. One must be named and registered before any real deployment.</p>
        <p className="callout gray">This pilot is built against the conditions of the Protection of Personal Information Act (POPIA). It is not claimed to be compliant: that also needs registration, operator agreements and an appointed Information Officer. This notice is not legal advice.</p>
      </article>
    </>
  )
}
