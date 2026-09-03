import { AiLayer } from "@/components/landing/ai-layer";
import { Cta } from "@/components/landing/cta";
import { FeatureGrid } from "@/components/landing/feature-grid";
import { Footer } from "@/components/landing/footer";
import { Header } from "@/components/landing/header";
import { Hero } from "@/components/landing/hero";
import { Pricing } from "@/components/landing/pricing";
import { Workflow } from "@/components/landing/workflow";

export default function GreekOSLandingPage() {
  return (
    <main className="min-h-screen bg-background text-primary grid-pattern overflow-hidden selection:bg-accent/40">
      <Header />
      <Hero />
      <FeatureGrid />
      <AiLayer />
      <Workflow />
      <Pricing />
      <Cta />
      <Footer />
    </main>
  );
}
