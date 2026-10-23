import { useEffect, useState } from 'react'
import { api } from '../api'
import { speechCode, useLang, useT } from '../i18n'
import { Icon } from './Icon'

interface Recognition {
  lang: string
  interimResults: boolean
  maxAlternatives: number
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start: () => void
}
type RecognitionCtor = new () => Recognition
const recogniser = (): RecognitionCtor | undefined => {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

/** Speak instead of typing. Hidden where the browser cannot do it. Only the fact of use is counted. */
export function VoiceButton({ onText }: { onText: (text: string) => void }) {
  const { lang } = useLang()
  const t = useT()
  const [on, setOn] = useState(false)
  const Ctor = typeof window === 'undefined' ? undefined : recogniser()
  if (!Ctor) return null
  function start() {
    const r = new Ctor!()
    r.lang = speechCode(lang)
    r.interimResults = false
    r.maxAlternatives = 1
    r.onresult = (e) => onText(e.results[0][0].transcript)
    r.onend = () => setOn(false)
    r.onerror = () => setOn(false)
    setOn(true)
    r.start()
    api.voiceUsed('search').catch(() => undefined)
  }
  return (
    <button type="button" className={`voice-btn ${on ? 'on' : ''}`} onClick={start} aria-label={t('Speak instead of typing')}
      title={t('Speak instead of typing. In Chrome the audio is sent to Google to turn it into text.')}>
      <Icon name="mic" size={18} />
    </button>
  )
}

/** Reads a sentence aloud in the chosen language, using a voice already on the device. */
export function ReadAloud({ text }: { text: string }) {
  const { lang } = useLang()
  const t = useT()
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([])
  const [speaking, setSpeaking] = useState(false)
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window

  useEffect(() => {
    if (!supported) return
    const load = () => setVoices(window.speechSynthesis.getVoices())
    load()
    window.speechSynthesis.addEventListener('voiceschanged', load)
    return () => window.speechSynthesis.removeEventListener('voiceschanged', load)
  }, [supported])
  useEffect(() => () => { if (supported) window.speechSynthesis.cancel() }, [supported])

  if (!supported) return null
  const want = speechCode(lang).slice(0, 2)
  const voice = voices.find((v) => v.lang.toLowerCase().startsWith(want))
  const missing = lang !== 'en' && voices.length > 0 && !voice

  function speak() {
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return }
    const u = new SpeechSynthesisUtterance(text)
    if (voice) { u.voice = voice; u.lang = voice.lang } else u.lang = speechCode(lang)
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    setSpeaking(true)
    window.speechSynthesis.speak(u)
    api.voiceUsed('read_aloud').catch(() => undefined)
  }
  return (
    <button type="button" className={`read-aloud ${speaking ? 'on' : ''}`} onClick={speak} disabled={missing}
      title={missing ? t('No voice for this language is installed on this device.') : t('Read this aloud')} aria-label={t('Read this aloud')}>
      <Icon name="volume" size={18} /><span>{speaking ? t('Stop') : t('Listen')}</span>
    </button>
  )
}
