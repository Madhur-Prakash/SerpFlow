/**
 * Server-Sent Events for a run (sections 42, 69).
 *
 * Every frame this hook yields was published by the planner or the executor as
 * a stage actually completed. There is no timer here and no simulated
 * sequence: if the backend is slow, the pipeline sits on the stage it is
 * really on.
 */

import * as React from "react";

import { tokens } from "@/lib/api";
import type { RunEvent } from "@/types/api";

export interface PipelineStage {
  key: string;
  label: string;
  /** Section 69 lists these in order; the backend emits them in the same order. */
  description: string;
}

export const PIPELINE: PipelineStage[] = [
  {
    key: "analyzing_intent",
    label: "Analyzing intent",
    description: "Reading the request and normalising it.",
  },
  {
    key: "finding_candidates",
    label: "Finding candidate engines",
    description: "Embedding the intent and retrieving the top engines, plus their substitutes.",
  },
  {
    key: "synthesizing_parameters",
    label: "Synthesizing parameters",
    description: "Date normalisation, locale inference, entity resolution, parameter binding.",
  },
  {
    key: "inferring_freshness",
    label: "Inferring freshness requirements",
    description: "How fresh each step has to be for a cached entry to be acceptable.",
  },
  {
    key: "finding_paths",
    label: "Finding valid paths",
    description: "Walking typed dependency edges. The graph computes chains; the model does not.",
  },
  {
    key: "generating_candidates",
    label: "Generating candidate plans",
    description: "Multiple competing plans, not a single best path.",
  },
  {
    key: "inspecting_cache",
    label: "Inspecting cache state",
    description: "Checking every step of every candidate against all four cache layers.",
  },
  {
    key: "calculating_marginal_cost",
    label: "Calculating marginal cost",
    description: "Only the steps that actually need a live upstream call count.",
  },
  {
    key: "reranking_plans",
    label: "Re-ranking plans",
    description: "Ranking on marginal cost rather than cold cost. This is the thesis.",
  },
  {
    key: "checking_budget",
    label: "Checking budget",
    description: "Identifying which plans fit, and recording anything that was reduced.",
  },
  {
    key: "executing",
    label: "Executing required steps",
    description: "Exact, then semantic, then archive, then live.",
  },
];

export type StageStatus = "pending" | "running" | "complete" | "failed";

export interface StageState {
  status: StageStatus;
  elapsedMs: number;
  detail: Record<string, unknown>;
}

export interface RunStreamState {
  events: RunEvent[];
  stages: Record<string, StageState>;
  currentStage: string | null;
  finished: boolean;
  failed: boolean;
  error: { code: string; message: string } | null;
  summary: Record<string, unknown> | null;
  elapsedMs: number;
}

const initialState: RunStreamState = {
  events: [],
  stages: {},
  currentStage: null,
  finished: false,
  failed: false,
  error: null,
  summary: null,
  elapsedMs: 0,
};

export function useRunStream(runId: string | null) {
  const [state, setState] = React.useState<RunStreamState>(initialState);
  const sourceRef = React.useRef<EventSource | null>(null);

  const reset = React.useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
    setState(initialState);
  }, []);

  React.useEffect(() => {
    if (!runId) return;

    setState(initialState);

    // EventSource cannot set headers, so the access token travels as a query
    // parameter on this one endpoint. It is short-lived and the connection is
    // same-origin through the Vite proxy in development and the reverse proxy
    // in production.
    const token = tokens.access();
    const url =
      "/v1/runs/" + runId + "/stream" + (token ? "?access_token=" + encodeURIComponent(token) : "");

    const source = new EventSource(url, { withCredentials: false });
    sourceRef.current = source;

    const handle = (raw: MessageEvent<string>) => {
      let event: RunEvent;
      try {
        event = JSON.parse(raw.data) as RunEvent;
      } catch {
        return;
      }
      if (event.type === "heartbeat") return;

      setState((previous) => {
        const stages = { ...previous.stages };

        if (event.type === "stage" || event.stage === "executing") {
          const status: StageStatus =
            event.status === "complete" || event.status === "step_complete"
              ? "complete"
              : event.status === "failed"
                ? "failed"
                : "running";
          stages[event.stage] = {
            status:
              stages[event.stage]?.status === "complete" && status === "running"
                ? "complete"
                : status,
            elapsedMs: event.elapsed_ms,
            detail: { ...(stages[event.stage]?.detail ?? {}), ...event.detail },
          };

          // Everything before the stage now running must already have finished.
          const index = PIPELINE.findIndex((stage) => stage.key === event.stage);
          if (index > 0) {
            for (const earlier of PIPELINE.slice(0, index)) {
              if (!stages[earlier.key]) {
                stages[earlier.key] = {
                  status: "complete",
                  elapsedMs: event.elapsed_ms,
                  detail: {},
                };
              } else if (stages[earlier.key].status === "running") {
                stages[earlier.key] = { ...stages[earlier.key], status: "complete" };
              }
            }
          }
        }

        if (event.type === "complete") {
          for (const stage of PIPELINE) {
            if (stages[stage.key]?.status === "running") {
              stages[stage.key] = { ...stages[stage.key], status: "complete" };
            }
          }
        }

        if (event.type === "error" && previous.currentStage) {
          stages[previous.currentStage] = {
            ...(stages[previous.currentStage] ?? { elapsedMs: 0, detail: {} }),
            status: "failed",
          };
        }

        return {
          events: [...previous.events, event],
          stages,
          currentStage: event.type === "stage" ? event.stage : previous.currentStage,
          finished: event.type === "complete" || event.type === "error",
          failed: event.type === "error",
          error:
            event.type === "error"
              ? {
                  code: String(event.detail.code ?? "ERROR"),
                  message: String(event.detail.message ?? "The run failed."),
                }
              : previous.error,
          summary: event.type === "complete" ? event.detail : previous.summary,
          elapsedMs: Math.max(previous.elapsedMs, event.elapsed_ms),
        };
      });

      if (event.type === "complete" || event.type === "error") {
        source.close();
        sourceRef.current = null;
      }
    };

    source.addEventListener("stage", handle as EventListener);
    source.addEventListener("complete", handle as EventListener);
    source.addEventListener("error", handle as EventListener);
    source.addEventListener("heartbeat", handle as EventListener);
    source.onmessage = handle;

    source.onerror = () => {
      // A completed run closes the stream from the server side; that is not a
      // failure, so only surface an error if nothing arrived at all.
      setState((previous) =>
        previous.finished || previous.events.length > 0
          ? previous
          : {
              ...previous,
              failed: true,
              finished: true,
              error: {
                code: "STREAM_DISCONNECTED",
                message: "The event stream closed before any stage was reported.",
              },
            },
      );
      source.close();
      sourceRef.current = null;
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [runId]);

  return { ...state, reset };
}
