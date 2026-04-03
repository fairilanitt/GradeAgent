import Link from "next/link";

import { getJson } from "@/lib/api";

type RuntimeOverview = {
  app_name: string;
  model_router_provider: string;
  model_router_simple_model: string;
  model_router_standard_model: string;
  model_router_complex_model: string;
  browser_agent_provider: string;
  browser_agent_model: string;
  heuristic_fallback_enabled: boolean;
  temporal_enabled: boolean;
  browser_headless: boolean;
  counts: {
    assessments: number;
    submissions: number;
    grade_runs: number;
    browser_jobs: number;
    active_rubrics: number;
  };
};

const runtimeFallback: RuntimeOverview = {
  app_name: "GradeAgent API",
  model_router_provider: "google",
  model_router_simple_model: "gemini-3.1-flash-lite-preview",
  model_router_standard_model: "gemini-3.1-flash-lite-preview",
  model_router_complex_model: "gemini-3.1-pro-preview",
  browser_agent_provider: "google",
  browser_agent_model: "gemini-3.1-pro-preview",
  heuristic_fallback_enabled: true,
  temporal_enabled: false,
  browser_headless: true,
  counts: {
    assessments: 0,
    submissions: 0,
    grade_runs: 0,
    browser_jobs: 0,
    active_rubrics: 0
  }
};

const scoringSteps = [
  "Load teacher criteria for the current task.",
  "Classify the text as simple, standard, or complex.",
  "Route to Gemini Lite, Flash, or Pro.",
  "Return numeric points and evidence snippets.",
  "Let the browser agent type only the points field."
];

export default async function Home() {
  const runtime = (await getJson<RuntimeOverview>("/api/runtime/overview")) ?? runtimeFallback;

  return (
    <main className="terminalShell">
      <section className="terminalFrame">
        <div className="frameHeader">
          <span className="frameTitle">gradeagent@console</span>
          <span className="statusBadge">router online</span>
        </div>
        <p className="terminalPrompt">$ gradeagent status</p>
        <h1 className="heroTitle">Gemini-routed text grading for browser queues.</h1>
        <p className="cliLead">
          The system reads one short submission at a time, chooses the cheapest Gemini tier that should still
          handle the task reliably, returns the numeric score, and lets the browser agent enter only that number
          into the grading platform.
        </p>
        <div className="actionRow">
          <Link className="commandLink" href="/assessments/demo">
            open scoring-workspace
          </Link>
          <Link className="secondaryLink" href="/browser">
            open queue-console
          </Link>
        </div>
      </section>

      <section className="statGrid">
        <article className="statCard">
          <span className="statLabel">router provider</span>
          <strong className="statValue">{runtime.model_router_provider}</strong>
          <span className="statMeta">simple + standard + complex tiers active</span>
        </article>
        <article className="statCard">
          <span className="statLabel">simple model</span>
          <strong className="statValue">{runtime.model_router_simple_model}</strong>
          <span className="statMeta">best for words, phrases, and very short answers</span>
        </article>
        <article className="statCard">
          <span className="statLabel">browser agent</span>
          <strong className="statValue">{runtime.browser_agent_model}</strong>
          <span className="statMeta">DOM + screenshot navigation via browser-use</span>
        </article>
        <article className="statCard">
          <span className="statLabel">runtime counts</span>
          <strong className="statValue">{runtime.counts.grade_runs}</strong>
          <span className="statMeta">
            {runtime.counts.assessments} assessments | {runtime.counts.browser_jobs} browser jobs
          </span>
        </article>
      </section>

      <section className="consoleGrid">
        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">current flow</span>
            <span className="statusBadge">5 stages</span>
          </div>
          <ul className="stepList">
            {scoringSteps.map((step, index) => (
              <li className="stepItem" key={step}>
                <span className="stepStatus">0{index + 1}</span>
                <div>
                  <div className="stepName">stage_{index + 1}</div>
                  <div className="stepDetail">{step}</div>
                </div>
              </li>
            ))}
          </ul>
        </article>

        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">routing table</span>
            <span className="statusBadge">cost tuned</span>
          </div>
          <div className="routeTable">
            <div className="routeRow">
              <span className="stepName">simple</span>
              <strong className="routeModel">{runtime.model_router_simple_model}</strong>
              <span className="stepDetail">single words, short phrases, short one-line responses</span>
            </div>
            <div className="routeRow">
              <span className="stepName">standard</span>
              <strong className="routeModel">{runtime.model_router_standard_model}</strong>
              <span className="stepDetail">normal short answers using the same cheap 3.1 Lite model</span>
            </div>
            <div className="routeRow">
              <span className="stepName">complex</span>
              <strong className="routeModel">{runtime.model_router_complex_model}</strong>
              <span className="stepDetail">exam mode, long responses, or dense teacher guidance</span>
            </div>
          </div>
        </article>
      </section>

      <section className="consoleGrid">
        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">live runtime</span>
            <span className="statusBadge">{runtime.browser_headless ? "headless" : "headed"}</span>
          </div>
          <div className="metricList">
            <div className="metricRow">
              <span>active rubrics</span>
              <strong>{runtime.counts.active_rubrics}</strong>
            </div>
            <div className="metricRow">
              <span>submissions stored</span>
              <strong>{runtime.counts.submissions}</strong>
            </div>
            <div className="metricRow">
              <span>temporal enabled</span>
              <strong>{runtime.temporal_enabled ? "yes" : "no"}</strong>
            </div>
            <div className="metricRow">
              <span>heuristic fallback</span>
              <strong>{runtime.heuristic_fallback_enabled ? "available" : "disabled"}</strong>
            </div>
          </div>
        </article>

        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">quick start</span>
            <span className="statusBadge">copy/paste</span>
          </div>
          <pre className="terminalPre">{`Copy-Item .env.example .env
npm run dev:api
npm run dev:web

POST /api/text-scoring/score
POST /api/browser-tasks/grade-queue
GET  /api/runtime/overview`}</pre>
        </article>
      </section>
    </main>
  );
}
