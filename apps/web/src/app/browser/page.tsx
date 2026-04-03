import { getJson } from "@/lib/api";

type RuntimeOverview = {
  browser_agent_provider: string;
  browser_agent_model: string;
  browser_headless: boolean;
  counts: {
    browser_jobs: number;
    submissions: number;
  };
};

const runtimeFallback: RuntimeOverview = {
  browser_agent_provider: "google",
  browser_agent_model: "gemini-3.1-pro-preview",
  browser_headless: true,
  counts: {
    browser_jobs: 0,
    submissions: 0
  }
};

const queueSteps = [
  "Open the grading queue inside the target platform.",
  "Find the next ungraded word, phrase, or paragraph answer.",
  "Read the text from the page DOM and screenshot context.",
  "Apply the teacher criteria and request numeric points.",
  "Type only the score into the separate points field.",
  "Optionally click save if the platform requires it."
];

export default async function BrowserConsolePage() {
  const runtime = (await getJson<RuntimeOverview>("/api/runtime/overview")) ?? runtimeFallback;

  return (
    <main className="terminalShell">
      <section className="terminalFrame">
        <div className="frameHeader">
          <span className="frameTitle">browser@queue-console</span>
          <span className="statusBadge">agent ready</span>
        </div>
        <p className="terminalPrompt">$ gradeagent queue status</p>
        <h1 className="heroTitle">Browser worker for ungraded exercise queues.</h1>
        <p className="cliLead">
          This worker uses <code className="inlineCode">browser-use</code> with Playwright so the model can inspect
          live DOM structure and screenshots while it navigates the site. Browser navigation stays on Gemini Pro by
          default because page understanding and safe field targeting are the expensive part.
        </p>
      </section>

      <section className="statGrid">
        <article className="statCard">
          <span className="statLabel">agent provider</span>
          <strong className="statValue">{runtime.browser_agent_provider}</strong>
          <span className="statMeta">configured in .env</span>
        </article>
        <article className="statCard">
          <span className="statLabel">agent model</span>
          <strong className="statValue">{runtime.browser_agent_model}</strong>
          <span className="statMeta">used for DOM + screenshot reasoning</span>
        </article>
        <article className="statCard">
          <span className="statLabel">browser mode</span>
          <strong className="statValue">{runtime.browser_headless ? "headless" : "headed"}</strong>
          <span className="statMeta">flip BROWSER_HEADLESS to watch the run</span>
        </article>
        <article className="statCard">
          <span className="statLabel">jobs recorded</span>
          <strong className="statValue">{runtime.counts.browser_jobs}</strong>
          <span className="statMeta">{runtime.counts.submissions} submissions stored overall</span>
        </article>
      </section>

      <section className="consoleGrid">
        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">queue steps</span>
            <span className="statusBadge">6 actions</span>
          </div>
          <ul className="stepList">
            {queueSteps.map((step, index) => (
              <li className="stepItem" key={step}>
                <span className="stepStatus">0{index + 1}</span>
                <div>
                  <div className="stepName">queue_step_{index + 1}</div>
                  <div className="stepDetail">{step}</div>
                </div>
              </li>
            ))}
          </ul>
        </article>

        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">operator notes</span>
            <span className="statusBadge">safe defaults</span>
          </div>
          <div className="metricList">
            <div className="metricRow">
              <span>dry run</span>
              <strong>inspect without typing</strong>
            </div>
            <div className="metricRow">
              <span>submit after typing</span>
              <strong>optional</strong>
            </div>
            <div className="metricRow">
              <span>artifacts</span>
              <strong>screenshot + extracted page text</strong>
            </div>
            <div className="metricRow">
              <span>score entry rule</span>
              <strong>number only</strong>
            </div>
          </div>
        </article>
      </section>

      <section className="terminalFrame">
        <div className="frameHeader">
          <span className="frameTitle">queue command</span>
          <span className="statusBadge">api</span>
        </div>
        <pre className="terminalPre">{`POST /api/browser-tasks/grade-queue
{
  "target_url": "https://platform.example/queue",
  "task_title": "Vocabulary queue",
  "max_items": 3,
  "dry_run": true,
  "submit_after_typing": false,
  "criteria": [
    {
      "id": "accuracy",
      "label": "Accuracy",
      "description": "Does the answer match the expected Swedish meaning?",
      "max_score": 2,
      "weight": 1
    }
  ]
}`}</pre>
      </section>
    </main>
  );
}
