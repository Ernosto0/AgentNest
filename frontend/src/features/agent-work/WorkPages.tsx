import { useState, type ReactNode } from "react";

import { useTranslation } from "react-i18next";

import { Link, useParams, useSearchParams } from "react-router-dom";

import { Button } from "@/components/Button";

import { Card } from "@/components/Card";

import { ErrorMessage } from "@/components/ErrorMessage";

import { SimulatedBadge } from "@/components/SimulatedBadge";

import { useSocialAccounts } from "@/features/inbox/hooks";

import { useCurrentWorkspace } from "@/features/workspaces/context";

import { actionLabelKey, type Schema } from "@/features/agent/hooks";

import { newRequestId } from "@/features/commands/hooks";

import {

  useAnswerQuestion,

  useAnswerTask,

  useChangeMemory,

  useCommentMedia,

  useComments,

  useMemory,

  useMemorySources,

  useQuestion,

  useQuestionAnswers,

  useQuestions,

  useTask,

  useThreadControl,

  useWorkThreads,

  useSelections,

  useManualModeration,

  useModerationOperations,

} from "./hooks";



const INPUT = "mt-1 block w-full min-w-0 rounded-control border border-border bg-surface px-3 py-2 text-primary placeholder:text-secondary focus-visible:outline-2 focus-visible:outline-focus focus:border-control";

const LINK = "text-action font-medium hover:text-action-hover underline";

function LocalTime({ value }: { value: string }) {

  const { i18n } = useTranslation();

  const { workspace } = useCurrentWorkspace();

  return (

    <time dateTime={value}>

      {new Date(value).toLocaleString(i18n.language, {

        timeZone: workspace.timezone,

        dateStyle: "short",

        timeStyle: "short",

      })}

    </time>

  );

}

export function WorkState({ state }: { state: string }) {
  const { t } = useTranslation();
  return (
    <span
      data-status={state}
      className={`inline-flex items-center rounded-control px-2.5 py-0.5 text-xs font-semibold border ${
        state === "answered" || state === "active" || state === "succeeded" || state === "visible"
          ? "bg-success-subtle text-success border-border"
          : state === "expired" || state === "redacted" || state === "deleted"
            ? "bg-surface text-secondary border-border"
            : state === "hidden"
              ? "bg-surface-subtle text-secondary border-border"
              : "bg-attention-subtle text-attention border-border"
      }`}
    >
      {t(`agentWork.commentState.${state}`, {
        defaultValue: t(`agentWork.state.${state}`, { defaultValue: t("agentWork.state.unknown") }),
      })}
    </span>
  );
}



function WorkFrame({

  children,

  titleKey,

}: {

  children: (account: string) => ReactNode;

  titleKey: string;

}) {

  const { t } = useTranslation();

  const { workspace } = useCurrentWorkspace();

  const [params, setParams] = useSearchParams();

  const accounts = useSocialAccounts(workspace.id);

  const account = params.get("account") ?? accounts.data?.[0]?.id ?? "";

  return (

    <div className="flex min-w-0 flex-col gap-6 max-w-4xl">

      <div>

        <Link className={LINK} to={`/w/${workspace.id}/more/agent?account=${account}`}>

          ← {t("agentWork.back")}

        </Link>

      </div>

      <div>

        <h1 className="text-2xl font-heading font-semibold text-primary">{t(titleKey)}</h1>

      </div>

      {accounts.error ? <ErrorMessage error={accounts.error} /> : null}

      {accounts.data?.length ? (

        <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">

          <span>{t("agentWork.account")}</span>

          <select

            className="w-full sm:w-80 rounded-control border border-border bg-surface px-3 py-2 text-base text-primary shadow-xs focus-visible:outline-2 focus-visible:outline-focus"

            value={account}

            onChange={(e) => setParams({ account: e.target.value })}

          >

            {accounts.data.map((a) => (

              <option key={a.id} value={a.id}>

                @{a.username ?? t("agentWork.account")}

              </option>

            ))}

          </select>

        </label>

      ) : accounts.isPending ? (

        <p role="status" className="text-sm text-secondary">

          {t("common.loading")}

        </p>

      ) : !accounts.error ? (

        <p className="text-sm text-secondary">{t("agentWork.noAccount")}</p>

      ) : null}

      {account ? children(account) : null}

    </div>

  );

}



export function QuestionsPage() {

  return (

    <WorkFrame titleKey="agentWork.questions">

      {(account) => <QuestionList key={account} account={account} />}

    </WorkFrame>

  );

}



function QuestionList({ account }: { account: string }) {

  const { t } = useTranslation();

  const { workspace } = useCurrentWorkspace();

  const [cursor, setCursor] = useState<string>();

  const questions = useQuestions(workspace.id, account, cursor);

  return (

    <div className="flex flex-col gap-4">

      {questions.isPending ? (

        <p role="status" className="text-sm text-secondary">

          {t("common.loading")}

        </p>

      ) : null}

      {questions.error ? <ErrorMessage error={questions.error} /> : null}

      <ul className="flex flex-col gap-3">

        {questions.data?.items.map((q) => (

          <li

            key={q.id}

            className="rounded-panel border border-border bg-surface p-4 shadow-xs flex flex-col gap-2.5 transition-colors hover:border-control"

          >

            <Link

              className="text-base font-semibold text-action hover:text-action-hover underline break-words"

              to={`/w/${workspace.id}/more/agent/questions/${q.id}?account=${account}`}

            >

              {q.body ?? t("agentWork.removed")}

            </Link>

            <div className="flex flex-wrap items-center gap-3 text-sm text-secondary">

              <WorkState state={q.state} />

              <span>·</span>

              <span>

                {t("agentWork.expires")} <LocalTime value={q.expires_at} />

              </span>

            </div>

          </li>

        ))}

      </ul>

      {questions.data?.items.length === 0 ? (

        <p className="text-sm text-secondary">{t("agentWork.emptyQuestions")}</p>

      ) : null}

      {questions.data?.next_cursor ? (

        <div>

          <Button variant="secondary" onClick={() => setCursor(questions.data!.next_cursor!)}>

            {t("agentWork.next")}

          </Button>

        </div>

      ) : null}

    </div>

  );

}



export function QuestionPage() {

  return (

    <WorkFrame titleKey="agentWork.question">

      {(account) => <QuestionDetail key={account} account={account} />}

    </WorkFrame>

  );

}



function QuestionDetail({ account }: { account: string }) {

  const { questionId = "" } = useParams();

  const { workspace, role } = useCurrentWorkspace();

  const { t } = useTranslation();

  const question = useQuestion(workspace.id, account, questionId);

  const [answerCursor, setAnswerCursor] = useState<string>();

  const answers = useQuestionAnswers(workspace.id, account, questionId, answerCursor);

  const answer = useAnswerQuestion(workspace.id, account, questionId);

  const [body, setBody] = useState("");

  const [reuse, setReuse] = useState(false);

  const [key, setKey] = useState("");

  const [request, setRequest] = useState(newRequestId);

  const [sent, setSent] = useState(false);

  const canAnswer = role !== "staff";

  if (question.isPending) {

    return (

      <p role="status" className="text-sm text-secondary">

        {t("common.loading")}

      </p>

    );

  }

  if (question.isError) return <ErrorMessage error={question.error} />;

  const q = question.data;

  return (

    <div className="flex flex-col gap-6">

      <div className="rounded-control border border-attention bg-attention-subtle p-3.5 text-sm font-medium text-attention shadow-xs">

        {t("agentWork.informationOnly")}

      </div>

      <Card className="flex flex-col gap-3">

        <p className="whitespace-pre-wrap break-words text-base text-primary font-medium">

          {q.body ?? t("agentWork.removed")}

        </p>

        <div className="flex flex-wrap items-center gap-3 text-sm text-secondary">

          <WorkState state={q.state} />

          <span>·</span>

          <span>{t(`agentWork.visibility.${q.visibility}`)}</span>

          <span>·</span>

          <span>

            {t("agentWork.expires")} <LocalTime value={q.expires_at} />

          </span>

        </div>

        {q.state === "answered" ? (

          <p role="status" className="text-sm font-medium text-success">

            {t("agentWork.alreadyAnswered")}

          </p>

        ) : null}

        <div>

          <Link

            className={LINK}

            to={`/w/${workspace.id}/more/agent/memory/${q.customer_id}?account=${account}`}

          >

            {t("agentWork.memory")}

          </Link>

        </div>

      </Card>



      {q.state === "pending" && !sent ? (

        <form

          className="flex flex-col gap-4 rounded-panel border border-border bg-surface p-4 shadow-xs"

          onSubmit={(e) => {

            e.preventDefault();

            answer.mutate(

              {

                body,

                expected_version: q.version,

                client_request_id: request,

                kind: canAnswer ? "answer" : "proposal",

                reusable_knowledge:

                  reuse && canAnswer ? { key: `custom.${key}`, text: body } : null,

              },

              {

                onSuccess: () => {

                  setSent(true);

                  setBody("");

                  setRequest(newRequestId());

                },

              },

            );

          }}

        >

          <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">

            <span>{canAnswer ? t("agentWork.answer") : t("agentWork.proposal")}</span>

            <textarea

              className={INPUT}

              rows={4}

              maxLength={reuse ? 500 : 700}

              required

              value={body}

              onChange={(e) => {

                setBody(e.target.value);

                setRequest(newRequestId());

              }}

            />

          </label>

          {canAnswer && q.visibility === "customer_reply" ? (

            <div className="flex flex-col gap-3 rounded-control border border-border bg-surface-subtle p-3.5">

              <label className="flex items-center gap-2 text-sm font-medium text-primary cursor-pointer">

                <input

                  type="checkbox"

                  className="h-4 w-4 rounded-control border-border text-action focus-visible:outline-2 focus-visible:outline-focus"

                  checked={reuse}

                  onChange={(e) => setReuse(e.target.checked)}

                />

                <span>{t("agentWork.reuse")}</span>

              </label>

              {reuse ? (

                <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">

                  <span>{t("agentWork.knowledgeKey")}</span>

                  <input

                    className={INPUT}

                    required

                    pattern="[a-z][a-z0-9_]{0,60}"

                    value={key}

                    onChange={(e) => setKey(e.target.value)}

                  />

                </label>

              ) : null}

            </div>

          ) : null}

          <div>

            <Button disabled={answer.isPending || !body.trim()} type="submit">

              {canAnswer ? t("agentWork.sendAnswer") : t("agentWork.sendProposal")}

            </Button>

          </div>

        </form>

      ) : null}



      {sent ? (

        <p role="status" className="text-sm font-medium text-success">

          {t("agentWork.answerRecorded")}

        </p>

      ) : null}

      {answer.error ? <ErrorMessage error={answer.error} /> : null}



      <Card className="flex flex-col gap-3">

        <div className="border-b border-border pb-3">

          <h2 className="text-lg font-heading font-semibold text-primary">{t("agentWork.answerHistory")}</h2>

        </div>

        {answers.error ? <ErrorMessage error={answers.error} /> : null}

        <ul className="flex flex-col gap-2">

          {answers.data?.items.map((a) => (

            <li

              key={a.id}

              className="rounded-control border border-border bg-surface-subtle p-3.5 flex flex-col gap-1.5 shadow-xs"

            >

              <span className="text-xs font-semibold text-secondary">

                {t(`agentWork.answerKind.${a.kind}`)} · {t(`agentWork.role.${a.author_role}`)}

              </span>

              <p className="break-words whitespace-pre-wrap text-sm text-primary font-medium">

                {a.body ?? t("agentWork.removed")}

              </p>

              {a.candidate_id ? <p className="text-xs text-secondary">{t("agentWork.candidate")}</p> : null}

            </li>

          ))}

        </ul>



        {answers.data?.next_cursor ? (

          <div>

            <Button variant="secondary" onClick={() => setAnswerCursor(answers.data!.next_cursor!)}>

              {t("agentWork.next")}

            </Button>

          </div>

        ) : null}

        <div className="pt-2">

          <Link className={LINK} to={`/w/${workspace.id}/approvals`}>

            {t("agentWork.approvals")}

          </Link>

        </div>

      </Card>

    </div>

  );

}



export function MemoryPage() {

  return (

    <WorkFrame titleKey="agentWork.memory">

      {(account) => <MemoryDetail key={account} account={account} />}

    </WorkFrame>

  );

}

function MemoryDetail({ account }: { account: string }) {
  const { customerId = "" } = useParams();
  const { workspace, role } = useCurrentWorkspace();
  const { t } = useTranslation();
  const [cursor, setCursor] = useState<string>();
  const memories = useMemory(workspace.id, account, customerId, cursor);
  const [sourceCursor, setSourceCursor] = useState<string>();
  const sources = useMemorySources(workspace.id, account, customerId, sourceCursor);
  const change = useChangeMemory(workspace.id, account, customerId);
  const [editing, setEditing] = useState<string>();
  const [body, setBody] = useState("");

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-panel border border-border bg-surface p-4 sm:p-5 shadow-xs flex flex-col gap-2.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-secondary">
              {t("agentWork.customerScope")}
            </span>
            <span className="rounded-control bg-surface-subtle px-2.5 py-0.5 text-xs font-mono font-medium text-primary border border-border">
              {customerId}
            </span>
          </div>
          <span className="inline-flex items-center rounded-control bg-surface-subtle px-2.5 py-0.5 text-xs font-medium text-secondary border border-border">
            🔒 {t("agentWork.memory")}
          </span>
        </div>
        <p className="text-sm text-secondary leading-relaxed">
          {t("agentWork.memoryIntro")}
        </p>
      </div>

      {memories.isPending ? (
        <p role="status" className="text-sm text-secondary">
          {t("common.loading")}
        </p>
      ) : null}

      {memories.error ? <ErrorMessage error={memories.error} /> : null}
      {change.error ? <ErrorMessage error={change.error} /> : null}
      {sources.error ? <ErrorMessage error={sources.error} /> : null}

      <ul className="flex flex-col gap-4">
        {memories.data?.items.map((m) => (
          <li
            key={m.id}
            className="rounded-panel border border-border bg-surface p-4 sm:p-5 shadow-xs flex flex-col gap-3.5 transition-colors hover:border-control"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-secondary">
                  {m.topic ?? m.kind ?? t("agentWork.memory")}
                </span>
                <span className="text-xs text-secondary">
                  · {t("agentWork.version")} {m.version}
                </span>
              </div>
              <span className="text-xs text-secondary">
                {t("agentWork.expires")} <LocalTime value={m.expires_at} />
              </span>
            </div>

            <p className="text-base text-primary whitespace-pre-wrap break-words leading-relaxed font-medium">
              {m.body ?? t("agentWork.removed")}
            </p>

            {role !== "staff" && m.body ? (
              <div className="flex flex-wrap gap-2 pt-1 border-t border-border/40">
                <Button
                  variant="secondary"
                  disabled={change.isPending}
                  onClick={() => {
                    setEditing(m.id);
                    setBody(m.body ?? "");
                  }}
                >
                  {t("agentWork.correct")}
                </Button>
                <Button
                  variant="secondary"
                  disabled={change.isPending}
                  onClick={() => change.mutate({ id: m.id, version: m.version })}
                >
                  {t("agentWork.forget")}
                </Button>
              </div>
            ) : null}

            {editing === m.id ? (
              <form
                className="rounded-panel border border-border bg-surface-subtle p-4 flex flex-col gap-3 shadow-xs"
                onSubmit={(e) => {
                  e.preventDefault();
                  change.mutate(
                    { id: m.id, version: m.version, body },
                    { onSuccess: () => setEditing(undefined) },
                  );
                }}
              >
                <label className="flex flex-col gap-1.5 text-sm font-medium text-secondary">
                  <span className="text-primary">{t("agentWork.correction")}</span>
                  <textarea
                    className={INPUT}
                    value={body}
                    onChange={(e) => setBody(e.target.value)}
                    minLength={3}
                    maxLength={240}
                    required
                  />
                </label>
                <div className="flex items-center gap-2">
                  <Button disabled={change.isPending} type="submit">
                    {t("agentWork.save")}
                  </Button>
                  <Button variant="ghost" type="button" onClick={() => setEditing(undefined)}>
                    {t("agentWork.dismiss")}
                  </Button>
                </div>
              </form>
            ) : null}

            <details className="border-t border-border pt-3">
              <summary className="min-h-11 cursor-pointer py-1 text-sm font-medium text-action hover:text-action-hover select-none">
                {t("agentWork.sources")}
              </summary>
              <div className="mt-2 flex flex-col gap-2">
                {sources.data?.items
                  .filter((s) => s.memory_id === m.id)
                  .map((s) => (
                    <div
                      key={s.id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-control bg-surface-subtle p-2.5 text-xs text-secondary border border-border"
                    >
                      <span className="font-medium text-primary">
                        {s.removed ? t("agentWork.sourceRemoved") : t("agentWork.sourceMessage")}
                      </span>
                      <LocalTime value={s.observed_at} />
                    </div>
                  ))}
              </div>
            </details>
          </li>
        ))}
      </ul>

      {memories.data?.items.length === 0 ? (
        <p className="text-sm text-secondary">{t("agentWork.emptyMemory")}</p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {memories.data?.next_cursor ? (
          <Button variant="secondary" onClick={() => setCursor(memories.data!.next_cursor!)}>
            {t("agentWork.next")}
          </Button>
        ) : null}

        {sources.data?.next_cursor ? (
          <Button variant="ghost" onClick={() => setSourceCursor(sources.data!.next_cursor!)}>
            {t("agentWork.moreSources")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export function ThreadSummary({
  thread,
  account,
}: {
  thread: Schema<"WorkThreadOut">;
  account: string;
}) {
  const { workspace } = useCurrentWorkspace();
  const { t } = useTranslation();
  const control = useThreadControl(workspace.id, account);

  return (
    <section
      aria-label={t("agentWork.agentWork")}
      className="rounded-panel border border-border bg-surface p-4 sm:p-5 shadow-xs flex flex-col gap-3.5"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <strong className="font-heading font-semibold text-primary">{t("agentWork.agentWork")}</strong>
          {thread.is_simulated ? <SimulatedBadge /> : null}
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center rounded-control bg-surface-subtle px-2.5 py-0.5 text-xs font-medium text-secondary border border-border">
            {t(thread.handling_mode === "human" ? "agentWork.human" : "agentWork.agent")}
          </span>
          <WorkState state={thread.state} />
        </div>
      </div>

      {thread.goal ? (
        <div className="flex items-center gap-2 text-sm text-secondary">
          <span className="font-medium text-primary">{t("agentWork.goalState")}</span>
          <WorkState state={thread.goal} />
        </div>
      ) : null}

      {thread.surface === "comment" ? (
        <div className="pt-0.5">
          <Button
            variant={thread.handling_mode === "human" ? "primary" : "secondary"}
            disabled={control.isPending}
            onClick={() =>
              control.mutate({
                id: thread.id,
                version: thread.version,
                mode: thread.handling_mode === "human" ? "agent" : "human",
              })
            }
          >
            {t(thread.handling_mode === "human" ? "convo.release" : "convo.takeover")}
          </Button>
        </div>
      ) : null}

      {control.error ? <ErrorMessage error={control.error} /> : null}

      {thread.customer_id && thread.surface === "dm" ? (
        <Link
          className={LINK}
          to={`/w/${workspace.id}/more/agent/memory/${thread.customer_id}?account=${account}`}
        >
          {t("agentWork.memory")}
        </Link>
      ) : null}

      {thread.actions.length > 0 ? (
        <div className="border-t border-border pt-3 flex flex-col gap-2">
          <ul className="flex flex-col gap-2">
            {thread.actions.map((a) => (
              <li
                key={a.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-control bg-surface-subtle px-3 py-2 text-sm border border-border"
              >
                <span className="font-medium text-primary">{t(actionLabelKey(a.action_type))}: </span>
                <div className="flex items-center gap-2">
                  <WorkState state={a.status} />
                  {a.is_simulated ? <SimulatedBadge /> : null}
                  {a.approval_id ? (
                    <Link className={`ml-2 ${LINK}`} to={`/w/${workspace.id}/approvals`}>
                      {t("agentWork.approvals")}
                    </Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export function ConversationAgentWork({

  account,

  conversation,

}: {

  account: string;

  conversation: string;

}) {

  const { workspace } = useCurrentWorkspace();

  const threads = useWorkThreads(workspace.id, account, conversation);

  return (

    <>

      {threads.data?.items.map((thread) => (

        <ThreadSummary key={thread.id} thread={thread} account={account} />

      ))}

    </>

  );

}

export function CommentsPage() {
  return (
    <WorkFrame titleKey="agentWork.comments">
      {(account) => <CommentList key={account} account={account} />}
    </WorkFrame>
  );
}

function CommentList({ account }: { account: string }) {
  const { workspace } = useCurrentWorkspace();
  const { t } = useTranslation();
  const [cursor, setCursor] = useState<string>();
  const comments = useComments(workspace.id, account, cursor);

  return (
    <div className="flex flex-col gap-4">
      <div
        role="note"
        className="rounded-panel border border-border bg-surface p-4 text-sm text-secondary flex items-start gap-3 shadow-xs"
      >
        <span className="text-base select-none" aria-hidden="true">
          ℹ️
        </span>
        <p className="leading-relaxed">{t("agentWork.publicNotice")}</p>
      </div>

      {comments.isPending ? (
        <p role="status" className="text-sm text-secondary">
          {t("common.loading")}
        </p>
      ) : null}

      {comments.error ? <ErrorMessage error={comments.error} /> : null}

      <ul className="flex flex-col gap-3">
        {comments.data?.items.map((c) => (
          <li
            key={c.id}
            className="rounded-panel border border-border bg-surface p-4 shadow-xs flex flex-col gap-2.5 transition-colors hover:border-control"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-secondary">
                {t(c.is_owner ? "agentWork.nativeOwner" : "agentWork.customer")}
              </span>
              <div className="flex items-center gap-2">
                <WorkState state={c.state} />
                {c.is_simulated ? <SimulatedBadge /> : null}
              </div>
            </div>

            <Link
              className="text-base font-semibold text-action hover:text-action-hover underline break-words"
              to={`/w/${workspace.id}/more/agent/comments/${c.thread_id}?account=${account}`}
            >
              {c.text ?? t("agentWork.removed")}
            </Link>
          </li>
        ))}
      </ul>

      {comments.data?.items.length === 0 ? (
        <p className="text-sm text-secondary">{t("agentWork.emptyComments")}</p>
      ) : null}

      {comments.data?.next_cursor ? (
        <div>
          <Button variant="secondary" onClick={() => setCursor(comments.data!.next_cursor!)}>
            {t("agentWork.next")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function CommentThreadPage() {
  return (
    <WorkFrame titleKey="agentWork.commentThread">
      {(account) => <CommentThread key={account} account={account} />}
    </WorkFrame>
  );
}

function CommentThread({ account }: { account: string }) {
  const { workspace } = useCurrentWorkspace();
  const { t } = useTranslation();
  const { threadId = "" } = useParams();
  const [cursor, setCursor] = useState<string>();
  const comments = useComments(workspace.id, account, cursor, threadId);
  const threads = useWorkThreads(workspace.id, account, threadId);
  const media = useCommentMedia(workspace.id, account, comments.data?.items[0]?.media_id ?? "");

  return (
    <div className="flex flex-col gap-5">
      <div
        role="note"
        className="rounded-panel border border-border bg-surface p-4 text-sm text-secondary flex items-start gap-3 shadow-xs"
      >
        <span className="text-base select-none" aria-hidden="true">
          ℹ️
        </span>
        <p className="leading-relaxed">{t("agentWork.publicNotice")}</p>
      </div>

      {media.data ? (
        <section
          aria-labelledby="comment-post-context-heading"
          className="rounded-panel border border-border bg-surface p-4 sm:p-5 shadow-xs flex flex-col gap-2.5"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="comment-post-context-heading" className="text-lg font-heading font-semibold text-primary">
              {t("agentWork.post")}
            </h2>
            <div className="flex items-center gap-2">
              <WorkState state={media.data.state} />
              {media.data.is_simulated ? <SimulatedBadge /> : null}
            </div>
          </div>
          <p className="text-base text-primary whitespace-pre-wrap break-words leading-relaxed">
            {media.data.caption ?? t("agentWork.removed")}
          </p>
        </section>
      ) : null}

      {comments.error ? <ErrorMessage error={comments.error} /> : null}

      {threads.data?.items.map((thread) => (
        <ThreadSummary key={thread.id} thread={thread} account={account} />
      ))}

      <section aria-label={t("agentWork.comments")} className="flex flex-col gap-3">
        <h2 className="text-lg font-heading font-semibold text-primary">{t("agentWork.comments")}</h2>
        <ol className="flex flex-col gap-4">
          {comments.data?.items.map((c) => (
            <li
              key={c.id}
              className="rounded-panel border border-border bg-surface p-4 sm:p-5 shadow-xs flex flex-col gap-3.5"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-secondary">
                  {t(c.is_owner ? "agentWork.nativeOwner" : "agentWork.customer")}
                </span>
                <div className="flex items-center gap-2">
                  <WorkState state={c.state} />
                  {c.is_simulated ? <SimulatedBadge /> : null}
                </div>
              </div>
              <p className="text-base text-primary whitespace-pre-wrap break-words leading-relaxed">
                {c.text ?? t("agentWork.removed")}
              </p>
              <ManualActions account={account} comment={c} />
            </li>
          ))}
        </ol>
      </section>

      {comments.data?.next_cursor ? (
        <div>
          <Button variant="secondary" onClick={() => setCursor(comments.data!.next_cursor!)}>
            {t("agentWork.next")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function TaskPage() {

  return (

    <WorkFrame titleKey="agentWork.task">

      {(account) => <TaskDetail key={account} account={account} />}

    </WorkFrame>

  );

}

function TaskDetail({ account }: { account: string }) {

  const { taskId = "" } = useParams();

  const { workspace } = useCurrentWorkspace();

  const { t } = useTranslation();

  const task = useTask(workspace.id, account, taskId);

  const answer = useAnswerTask(workspace.id, account, taskId);

  const [body, setBody] = useState("");

  const [media, setMedia] = useState("");

  const [content, setContent] = useState("");

  const [request, setRequest] = useState(newRequestId);

  if (task.isPending) return <p>{t("common.loading")}</p>;

  if (task.isError) return <ErrorMessage error={task.error} />;

  const item = task.data;

  return (

    <>

      <WorkState state={item.status} />

      <p>{t("agentWork.taskIntro")}</p>

      {item.clarification && item.question_version ? (

        <form

          className="flex flex-col gap-3.5 rounded-control border border-border bg-surface p-4 shadow-xs"

          onSubmit={(e) => {

            e.preventDefault();

            answer.mutate(

              {

                text: body,

                client_request_id: request,

                expected_version: item.question_version!,

                media_asset_id: media || null,

                content_id: content || null,

              },

              {

                onSuccess: () => {

                  setBody("");

                  setRequest(newRequestId());

                },

              },

            );

          }}

        >

          <p className="break-words">{item.clarification}</p>

          <label>

            {t("agentWork.clarification")}

            <textarea

              required

              className={INPUT}

              value={body}

              onChange={(e) => {

                setBody(e.target.value);

                setRequest(newRequestId());

              }}

              maxLength={4000}

            />

          </label>

          <label>

            {t("agentWork.mediaSelection")}

            <TaskSelection account={account} kind="media" value={media} onChange={value=>{setMedia(value);setRequest(newRequestId());}} />

          </label>

          <label>

            {t("agentWork.contentSelection")}

            <TaskSelection account={account} kind="content" value={content} onChange={value=>{setContent(value);setRequest(newRequestId());}} />

          </label>

          <Button disabled={answer.isPending || !body.trim()} type="submit">

            {t("agentWork.sendClarification")}

          </Button>

        </form>

      ) : null}

      {answer.error ? <ErrorMessage error={answer.error} /> : null}

      <ul>

        {item.actions.map((a) => (

          <li key={a.action_id} className="my-3 rounded-control border border-border bg-surface-subtle p-3.5 shadow-xs">

            <p>{t(actionLabelKey(a.action_type))}</p>

            <WorkState state={a.content_status ?? a.status} />

            {a.is_simulated ? <SimulatedBadge /> : null}

            {a.approval_id ? (

              <Link className={`block ${LINK}`} to={`/w/${workspace.id}/approvals`}>

                {t("agentWork.approvals")}

              </Link>

            ) : null}

            {a.content_id ? (

              <Link className={`block ${LINK}`} to={`/w/${workspace.id}/content/${a.content_id}`}>

                {t("agentWork.openContent")}

              </Link>

            ) : null}

          </li>

        ))}

      </ul>

    </>

  );

}



function TaskSelection({

  account,

  kind,

  value,

  onChange,

}: {

  account: string;

  kind: "media" | "content";

  value: string;

  onChange: (value: string) => void;

}) {

  const { workspace } = useCurrentWorkspace();

  const { t } = useTranslation();

  const [cursor, setCursor] = useState<string>();

  const choices = useSelections(workspace.id, account, kind, cursor);

  return (

    <>

      <select className={INPUT} value={value} onChange={(e) => onChange(e.target.value)}>

        <option value="">{t("agentWork.noSelection")}</option>

        {choices.data?.items.map((item) => (

          <option key={item.id} value={item.id}>

            {item.label}

          </option>

        ))}

      </select>

      {choices.data?.next_cursor ? (

        <Button type="button" onClick={() => setCursor(choices.data!.next_cursor!)}>

          {t("agentWork.next")}

        </Button>

      ) : null}

      {choices.error ? <ErrorMessage error={choices.error} /> : null}

    </>

  );

}

function ManualActions({ account, comment }: { account: string; comment: Schema<"CommentOut"> }) {
  const { workspace, role } = useCurrentWorkspace();
  const { t } = useTranslation();
  const mutation = useManualModeration(workspace.id, account, comment.id);
  const [operationCursor, setOperationCursor] = useState<string>();
  const operations = useModerationOperations(workspace.id, account, comment.id, operationCursor);
  const [confirm, setConfirm] = useState<"hide" | "unhide" | "delete">();
  const [request, setRequest] = useState(newRequestId);

  return (
    <div className="flex flex-col gap-3 pt-1">
      {operations.data?.items.length ? (
        <div className="rounded-panel bg-surface-subtle p-3.5 border border-border flex flex-col gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-secondary">
            {t("agentWork.operationHistory")}
          </span>
          <ul className="flex flex-col gap-2">
            {operations.data.items.map((op) => (
              <li
                key={op.operation_id}
                className="flex flex-wrap items-center justify-between gap-2 text-xs"
              >
                <span className="font-medium text-primary">
                  {t(`agentWork.manual.${op.effect}`)}:
                </span>
                <div className="flex items-center gap-2">
                  <WorkState state={op.status} />
                  {op.is_simulated ? <SimulatedBadge /> : null}
                </div>
              </li>
            ))}
          </ul>
          {operations.data?.next_cursor ? (
            <div>
              <Button
                variant="ghost"
                onClick={() => setOperationCursor(operations.data!.next_cursor!)}
              >
                {t("agentWork.next")}
              </Button>
            </div>
          ) : null}
        </div>
      ) : null}

      {role !== "staff" && !comment.is_owner && ["visible", "hidden"].includes(comment.state) ? (
        <div className="flex flex-wrap gap-2">
          {(comment.state === "hidden" ? (["unhide"] as const) : (["hide", "delete"] as const)).map(
            (effect) => (
              <Button
                key={effect}
                variant={effect === "delete" ? "danger" : "secondary"}
                disabled={mutation.isPending}
                onClick={() => {
                  setConfirm(effect);
                  setRequest(newRequestId());
                }}
              >
                {t(`agentWork.manual.${effect}`)}
              </Button>
            ),
          )}
        </div>
      ) : null}

      {confirm ? (
        <div
          role="alert"
          className="rounded-panel border border-border bg-surface p-4 flex flex-col gap-3 shadow-xs"
        >
          <p className="text-sm font-medium text-primary leading-relaxed">
            {t("agentWork.manualConfirm")}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant={confirm === "delete" ? "danger" : "primary"}
              disabled={mutation.isPending}
              onClick={() =>
                mutation.mutate(
                  { effect: confirm, expected_version: comment.version, client_request_id: request },
                  { onSuccess: () => setConfirm(undefined) },
                )
              }
            >
              {t("agentWork.confirmEffect")}
            </Button>
            <Button variant="ghost" onClick={() => setConfirm(undefined)}>
              {t("agentWork.dismiss")}
            </Button>
          </div>
        </div>
      ) : null}

      {mutation.error ? <ErrorMessage error={mutation.error} /> : null}
      {operations.error ? <ErrorMessage error={operations.error} /> : null}
    </div>
  );
}
