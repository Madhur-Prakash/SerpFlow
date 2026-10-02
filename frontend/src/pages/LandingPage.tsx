/**
 * The landing page.
 *
 * Ordered as an argument rather than a feature list: the claim, the stack it
 * runs on, the numbers, the problem it answers, the thesis told on scroll, how
 * the planner works, what the cache does, the measured evidence, the
 * capabilities, how to run it, and the questions that follow.
 */

import { SectionRail, type RailSection } from "@/components/marketing";
import { Hero, StackStrip } from "@/pages/landing/Hero";
import {
  Benchmark,
  CacheLayers,
  CallToAction,
  Capabilities,
  Faq,
  HowItWorks,
  Numbers,
  Problem,
  QuickStart,
} from "@/pages/landing/Sections";
import { ThesisStory } from "@/pages/landing/ThesisStory";

/** The rail's stops. Each id is a section on this page. */
const RAIL: RailSection[] = [
  { id: "problem", label: "Problem" },
  { id: "thesis", label: "Thesis" },
  { id: "how-it-works", label: "Planner" },
  { id: "cache", label: "Cache" },
  { id: "benchmark", label: "Evidence" },
  { id: "capabilities", label: "Features" },
  { id: "quick-start", label: "Run it" },
  { id: "faq", label: "Questions" },
];

export function LandingPage() {
  return (
    <>
      <SectionRail sections={RAIL} />
      <Hero />
      <StackStrip />
      <Numbers />
      <Problem />
      <ThesisStory />
      <HowItWorks />
      <CacheLayers />
      <Benchmark />
      <Capabilities />
      <QuickStart />
      <Faq />
      <CallToAction />
    </>
  );
}
