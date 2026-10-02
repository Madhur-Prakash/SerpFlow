/**
 * The landing page.
 *
 * Ordered as an argument rather than a feature list: the claim, the stack it
 * runs on, the numbers, the problem it answers, the thesis told on scroll, how
 * the planner works, what the cache does, the measured evidence, the
 * capabilities, how to run it, and the questions that follow.
 */

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

export function LandingPage() {
  return (
    <>
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
