import React, { useEffect } from "react";
import { Link } from "react-router-dom";
import { Search, ShieldCheck, Scale, FolderKanban, Sparkles, Smartphone, ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import LogoSVG from "./components/LogoSVG.jsx";
import { useLogoAnimation } from "./hooks/useLogoAnimation.js";

export default function LandingPage() {
  const { play } = useLogoAnimation();

  // Fire the logo entrance animation once on page load
  useEffect(() => {
    play('moderate');
  }, [play]);

  const municipalities = [
    { name: "Dallas", desc: "Residential & Commercial Codes" },
    { name: "Plano", desc: "Building & Zoning Ordinances" },
    { name: "Frisco", desc: "Development Standards" },
    { name: "McKinney", desc: "Municipal & Construction Codes" },
    { name: "Fort Worth", desc: "Comprehensive Safety Regs" }
  ];

  const features = [
    {
      icon: <Search className="h-6 w-6 text-accent" />,
      title: "Municipality Ordinance Searching",
      desc: "Ask compliance questions in plain English and receive instant, cited answers directly from municipal law databases."
    },
    {
      icon: <ShieldCheck className="h-6 w-6 text-accent" />,
      title: "AHJ Verification Notice",
      desc: "Automatically identifies the Authority Having Jurisdiction (AHJ) for your project address and links you directly to their validation portals."
    },
    {
      icon: <Scale className="h-6 w-6 text-accent" />,
      title: "Conflict Warning Systems",
      desc: "Instantly flags regulatory contradictions where municipal codes differ from Texas state or federal standards, reducing review delays."
    },
    {
      icon: <FolderKanban className="h-6 w-6 text-accent" />,
      title: "Project-Specific Workspaces",
      desc: "Save search histories, audit trails, and document libraries scoped to individual projects for clean team coordination."
    },
    {
      icon: <Smartphone className="h-6 w-6 text-accent" />,
      title: "AR Spatial Checks (Mobile)",
      desc: "On-site tools using AR to overlay code requirements, measure heights, highlight walls, and check setbacks in real-time."
    },
    {
      icon: <Sparkles className="h-6 w-6 text-accent" />,
      title: "Generative Room Preview",
      desc: "Take project scans, generate preview design images, and preview material overlays instantly via our built-in image models."
    }
  ];

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col font-sans">
      {/* Hero Section */}
      <section className="relative overflow-hidden pt-20 pb-16 md:pt-32 md:pb-24 border-b border-border bg-gradient-to-b from-background via-background/50 to-secondary/10">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 text-center space-y-8">
          {/* Animated hero logo */}
          <div className="flex justify-center mb-2">
            <LogoSVG animated className="hero-logo" aria-label="permit_rag logo" />
          </div>

          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-accent/20 bg-accent/5 text-accent text-xs font-semibold tracking-wide uppercase font-heading animate-fade-in">
            <Sparkles className="h-3.5 w-3.5" />
            RAG-Powered DFW Permit Compliance
          </div>
          
          <h1 className="text-4xl sm:text-5xl md:text-6xl font-black font-heading tracking-tight leading-none text-foreground max-w-4xl mx-auto">
            Municipality Ordinance <span className="text-accent bg-clip-text">Searching</span> Done in Seconds
          </h1>
          
          <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto font-normal leading-relaxed">
            Stop digging through thousands of pages of municipal code PDFs. Get instant, cited compliance answers for Dallas, Plano, Frisco, McKinney, and Fort Worth.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <Link to="/auth">
              <Button size="lg" className="w-full sm:w-auto px-8 font-semibold flex items-center gap-2 shadow-lg landing-hero-primary">
                Get Started Free
                <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <a href="#features">
              <Button variant="outline" size="lg" className="w-full sm:w-auto px-8 font-semibold landing-hero-outline">
                Learn More
              </Button>
            </a>
          </div>

          {/* DFW Badge Banner */}
          <div className="pt-12 md:pt-16">
            <p className="text-xs uppercase font-semibold tracking-wider text-muted-foreground mb-6">Supported DFW Municipalities</p>
            <div className="flex flex-wrap justify-center gap-3">
              {municipalities.map((city, index) => (
                <div 
                  key={index} 
                  className="px-4 py-2 bg-card border border-border rounded-xl text-sm font-medium hover:border-accent/40 hover:bg-secondary/10 transition-all cursor-default shadow-sm group"
                >
                  <span className="font-heading font-bold text-foreground block">{city.name}</span>
                  <span className="text-[10px] text-muted-foreground group-hover:text-accent transition-colors">{city.desc}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-16 md:py-24 max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 space-y-16">
        <div className="text-center space-y-4">
          <h2 className="text-3xl md:text-4xl font-extrabold font-heading tracking-tight">
            Compliance Intelligence Platform
          </h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Everything contractors, developers, and project managers need to clear inspections and secure permits quickly.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {features.map((feature, idx) => (
            <div 
              key={idx} 
              className="p-6 bg-card border border-border rounded-2xl hover:border-accent/30 hover:shadow-md transition-all space-y-4 shadow-sm"
            >
              <div className="p-3 bg-secondary/50 rounded-xl w-fit">
                {feature.icon}
              </div>
              <h3 className="text-lg font-bold font-heading text-foreground">{feature.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Metrics Section */}
      <section className="bg-secondary/20 border-y border-border py-16">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
          <div className="space-y-2">
            <div className="text-4xl font-extrabold font-heading text-accent">5 / 5</div>
            <div className="text-sm font-semibold uppercase text-muted-foreground tracking-wider">Top DFW Municipalities Covered</div>
          </div>
          <div className="space-y-2 border-y md:border-y-0 md:border-x border-border/80 py-6 md:py-0">
            <div className="text-4xl font-extrabold font-heading text-accent">10,000+</div>
            <div className="text-sm font-semibold uppercase text-muted-foreground tracking-wider">Indexed Regulatory Sections</div>
          </div>
          <div className="space-y-2">
            <div className="text-4xl font-extrabold font-heading text-accent">100%</div>
            <div className="text-sm font-semibold uppercase text-muted-foreground tracking-wider">Verifiable Citations Provided</div>
          </div>
        </div>
      </section>

      {/* CTA Banner */}
      <section className="py-20 md:py-24 text-center max-w-4xl mx-auto px-4 space-y-8">
        <h2 className="text-3xl sm:text-4xl font-extrabold font-heading tracking-tight">
          Ready to Streamline Your Permit Approvals?
        </h2>
        <p className="text-muted-foreground max-w-xl mx-auto leading-relaxed">
          Create an account to build projects, upload local documents, search ordinances, and run AR inspection scans.
        </p>
        <div className="pt-4">
          <Link to="/auth">
            <Button size="lg" className="px-10 font-bold text-base flex items-center gap-2 mx-auto">
              Get Started Now
              <ArrowRight className="h-5 w-5" />
            </Button>
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto border-t border-border py-8 bg-card">
        <div className="max-w-6xl mx-auto px-4 text-center text-xs text-muted-foreground space-y-2">
          <p>© {new Date().getFullYear()} permit_rag. All rights reserved.</p>
          <p>Disclaimer: permit_rag provides cited references for assistance only. Confirm all compliance decisions with local AHJ before building.</p>
        </div>
      </footer>
    </div>
  );
}
