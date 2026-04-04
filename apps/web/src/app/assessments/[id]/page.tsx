import { getJson } from "@/lib/api";

type GradeRun = {
  id: string;
  routing_tier: string;
  status: string;
  confidence: number;
  feedback_text: string;
  model_summary?: string | null;
  policy_flags_json: string[];
  audit_snapshot_json?: {
    model_provider?: string;
    model_name?: string;
    complexity_score?: number;
    routing_reasons?: string[];
  };
  result_json?: {
    overall_score: number;
    max_score: number;
    grade_band: string;
    criterion_scores: Array<{
      criterion_id: string;
      label: string;
      score: number;
      max_score: number;
      rationale: string;
      evidence: Array<{ excerpt: string; reason: string }>;
    }>;
  };
};

type ReviewPayload = {
  assessment: {
    id: string;
    title: string;
    task_type: string;
    release_mode: string;
  };
  rubric: {
    name: string;
    status: string;
  } | null;
  submissions: Array<{
    id: string;
    student_identifier: string;
    answer_text: string;
  }>;
  grade_runs: GradeRun[];
};

const demoPayload: ReviewPayload = {
  assessment: {
    id: "demo",
    title: "Demo text scoring workspace",
    task_type: "text_submission",
    release_mode: "score_entry"
  },
  rubric: {
    name: "Teacher-entered scoring criteria",
    status: "active"
  },
  submissions: [
    {
      id: "submission-demo",
      student_identifier: "student-demo",
      answer_text: "Jag tycker att svenska är viktigt eftersom vi behöver kommunikation i vardagen."
    }
  ],
  grade_runs: [
    {
      id: "grade-run-demo",
      routing_tier: "simple",
      status: "awaiting_review",
      confidence: 0.84,
      feedback_text: "Recommended score for entry into the platform points field.",
      model_summary: "google/gemini-2.5-flash-lite handled simple routing across 2 rubric criteria.",
      policy_flags_json: ["low_confidence"],
      audit_snapshot_json: {
        model_provider: "google",
        model_name: "gemini-2.5-flash-lite",
        complexity_score: 2,
        routing_reasons: ["short_response", "single_line_submission"]
      },
      result_json: {
        overall_score: 4,
        max_score: 5,
        grade_band: "B",
        criterion_scores: [
          {
            criterion_id: "topic",
            label: "Topic coverage",
            score: 2,
            max_score: 3,
            rationale: "The response addresses the topic directly.",
            evidence: [{ excerpt: "svenska är viktigt", reason: "Direct topical claim." }]
          },
          {
            criterion_id: "clarity",
            label: "Clarity",
            score: 2,
            max_score: 2,
            rationale: "Meaning is clear and easy to follow.",
            evidence: [{ excerpt: "kommunikation i vardagen", reason: "Shows practical framing." }]
          }
        ]
      }
    }
  ]
};

export default async function AssessmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const payload = (await getJson<ReviewPayload>(`/api/assessments/${id}/review`)) ?? demoPayload;
  const run = payload.grade_runs[0];
  const submission = payload.submissions[0];
  const points = run?.result_json?.overall_score ?? "-";
  const maxPoints = run?.result_json?.max_score ?? "-";
  const steps = [
    {
      name: "submission_loaded",
      detail: `Loaded answer from ${submission?.student_identifier ?? "unknown student"}.`
    },
    {
      name: "router_selected",
      detail: `${run?.routing_tier ?? "unknown"} routing via ${run?.audit_snapshot_json?.model_name ?? "unknown model"}.`
    },
    {
      name: "score_prepared",
      detail: `${points}/${maxPoints} points ready for entry.`
    },
    {
      name: "review_state",
      detail: `Run is currently ${run?.status ?? "unavailable"}.`
    }
  ];

  return (
    <main className="terminalShell">
      <section className="terminalFrame">
        <div className="frameHeader">
          <span className="frameTitle">scoring@workspace</span>
          <span className="statusBadge">{payload.rubric?.status ?? "no-rubric"}</span>
        </div>
        <p className="terminalPrompt">$ gradeagent review {payload.assessment.id}</p>
        <h1 className="heroTitle">{payload.assessment.title}</h1>
        <p className="cliLead">
          Task type: <code className="inlineCode">{payload.assessment.task_type}</code> | release mode:{" "}
          <code className="inlineCode">{payload.assessment.release_mode}</code> | rubric:{" "}
          <code className="inlineCode">{payload.rubric?.name ?? "none"}</code>
        </p>
      </section>

      <section className="statGrid">
        <article className="statCard">
          <span className="statLabel">points to enter</span>
          <strong className="statValue">
            {points}/{maxPoints}
          </strong>
          <span className="statMeta">{run?.result_json?.grade_band ?? "n/a"} grade band</span>
        </article>
        <article className="statCard">
          <span className="statLabel">routing tier</span>
          <strong className="statValue">{run?.routing_tier ?? "unknown"}</strong>
          <span className="statMeta">complexity score {run?.audit_snapshot_json?.complexity_score ?? "-"}</span>
        </article>
        <article className="statCard">
          <span className="statLabel">selected model</span>
          <strong className="statValue">{run?.audit_snapshot_json?.model_name ?? "unknown"}</strong>
          <span className="statMeta">{run?.audit_snapshot_json?.model_provider ?? "provider unavailable"}</span>
        </article>
        <article className="statCard">
          <span className="statLabel">confidence</span>
          <strong className="statValue">{run ? `${Math.round(run.confidence * 100)}%` : "-"}</strong>
          <span className="statMeta">{run?.status ?? "no run loaded"}</span>
        </article>
      </section>

      <section className="consoleGrid">
        <article className="terminalFrame submissionCard">
          <div className="frameHeader">
            <span className="frameTitle">submission text</span>
            <span className="statusBadge">{submission?.student_identifier ?? "unknown"}</span>
          </div>
          <p className="textBlock">{submission?.answer_text ?? "No answer loaded."}</p>
          <div className="tagList">
            {(run?.policy_flags_json ?? []).map((flag) => (
              <span className="tag" key={flag}>
                {flag}
              </span>
            ))}
          </div>
        </article>

        <article className="terminalFrame">
          <div className="frameHeader">
            <span className="frameTitle">run steps</span>
            <span className="statusBadge">review-safe</span>
          </div>
          <ul className="stepList">
            {steps.map((step, index) => (
              <li className="stepItem" key={step.name}>
                <span className="stepStatus">0{index + 1}</span>
                <div>
                  <div className="stepName">{step.name}</div>
                  <div className="stepDetail">{step.detail}</div>
                </div>
              </li>
            ))}
          </ul>
          <p className="tiny">{run?.model_summary ?? "No model summary available."}</p>
        </article>
      </section>

      <section className="terminalFrame">
        <div className="frameHeader">
          <span className="frameTitle">criterion breakdown</span>
          <span className="statusBadge">{run?.result_json?.criterion_scores.length ?? 0} items</span>
        </div>
        <div className="criterionGrid">
          {(run?.result_json?.criterion_scores ?? []).map((criterion) => (
            <article className="criterionCard" key={criterion.criterion_id}>
              <div className="criterionHeader">
                <div>
                  <div className="stepName">{criterion.label}</div>
                  <div className="stepDetail">{criterion.rationale}</div>
                </div>
                <span className="scoreChip">
                  {criterion.score}/{criterion.max_score}
                </span>
              </div>
              {criterion.evidence.map((evidence, index) => (
                <blockquote className="quoteBlock" key={`${criterion.criterion_id}-${index}`}>
                  <p>{evidence.excerpt}</p>
                  <span>{evidence.reason}</span>
                </blockquote>
              ))}
            </article>
          ))}
        </div>
        <p className="tiny">{run?.feedback_text ?? "No feedback available."}</p>
      </section>
    </main>
  );
}
