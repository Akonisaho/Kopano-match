import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireRole, useAuth } from './auth'
import Shell from './components/Shell'
import { isProvider } from './api'
import Landing from './pages/Landing'
import Privacy from './pages/Privacy'
import ResetPassword from './pages/ResetPassword'
import { MatchDetail, SecurityCentre } from './pages/Shared'
import { Applications, Consortia, Documents, Onboarding, SmeOpportunities, SmeOverview, SmeProfilePage, VerificationCentre } from './pages/Sme'
import { OpportunityDetail, PostOpportunity, ProviderOverview, ShortlistPage, SmeDirectory } from './pages/Provider'
import { AdminQueue } from './pages/Admin'
import { Dossier } from './pages/Dossier'
import { ImpactPage } from './pages/Impact'
import { UnlockMap } from './pages/Insights'
import { Ecosystem } from './pages/Ecosystem'
import { ProviderFeedback, SmeFeedback } from './pages/Feedback'
import ResponsibleAI from './pages/ResponsibleAI'
import PassportPage from './pages/PassportPage'

function Index() {
  const { me } = useAuth()
  if (!me) return null
  if (me.role === 'admin') return <Navigate to="/app/ecosystem" replace />
  return isProvider(me.role) ? <ProviderOverview /> : <SmeOverview />
}

function FeedbackRoute() {
  const { me } = useAuth()
  if (!me) return null
  return isProvider(me.role) ? <ProviderFeedback /> : <SmeFeedback />
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Landing initialAuth="login" />} />
      <Route path="/register" element={<Landing initialAuth="signup" />} />
      <Route path="/privacy" element={<Privacy />} />
      <Route path="/responsible-ai" element={<ResponsibleAI />} />
      <Route path="/passport/:token" element={<PassportPage />} />
      <Route path="/reset" element={<ResetPassword />} />
      <Route path="/onboarding" element={<RequireRole roles={['sme']}><Onboarding /></RequireRole>} />
      <Route path="/app" element={<RequireRole roles={['sme', 'corporate', 'funder', 'support', 'admin']}><Shell /></RequireRole>}>
        <Route index element={<Index />} />
        <Route path="profile" element={<RequireRole roles={['sme']}><SmeProfilePage /></RequireRole>} />
        <Route path="verification" element={<RequireRole roles={['sme']}><VerificationCentre /></RequireRole>} />
        <Route path="documents" element={<RequireRole roles={['sme']}><Documents /></RequireRole>} />
        <Route path="opportunities" element={<RequireRole roles={['sme']}><SmeOpportunities /></RequireRole>} />
        <Route path="applications" element={<Applications />} />
        <Route path="post" element={<RequireRole roles="provider"><PostOpportunity /></RequireRole>} />
        <Route path="opportunities/:id" element={<RequireRole roles="provider"><OpportunityDetail /></RequireRole>} />
        <Route path="shortlist" element={<RequireRole roles="provider"><ShortlistPage /></RequireRole>} />
        <Route path="smes" element={<RequireRole roles="provider"><SmeDirectory /></RequireRole>} />
        <Route path="insights" element={<RequireRole roles="provider"><UnlockMap /></RequireRole>} />
        <Route path="matches/:id/dossier" element={<Dossier />} />
        <Route path="impact" element={<RequireRole roles="provider"><ImpactPage /></RequireRole>} />
        <Route path="consortia" element={<RequireRole roles={['sme']}><Consortia /></RequireRole>} />
        <Route path="queue" element={<RequireRole roles={['admin']}><AdminQueue /></RequireRole>} />
        <Route path="ecosystem" element={<RequireRole roles={['admin']}><Ecosystem /></RequireRole>} />
        <Route path="feedback" element={<RequireRole roles={['sme', 'corporate', 'funder', 'support']}><FeedbackRoute /></RequireRole>} />
        <Route path="matches/:id" element={<MatchDetail />} />
        <Route path="security" element={<SecurityCentre />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
