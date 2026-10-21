import type { components } from "./schema";

type Schemas = components["schemas"];

export type Me = Schemas["MeResponse"];
export type Membership = Schemas["MembershipOut"];
export type Workspace = Schemas["WorkspaceOut"];
export type Role = Membership["role"];
export type Meta = Schemas["MetaResponse"];

export type Fact = Schemas["FactOut"];
export type FactCandidate = Schemas["CandidateOut"];
export type FactVersion = Schemas["VersionOut"];
export type TemplateItem = Schemas["TemplateItemOut"];
export type Readiness = Schemas["ReadinessOut"];
export type Requirement = Schemas["RequirementOut"];
export type FactCategory = Fact["category"];
export type FactState = Fact["state"];
export type FactCreateBody = Schemas["FactCreate"];
export type FactPatchBody = Schemas["FactPatch"];
export type WorkspaceCreateBody = Schemas["WorkspaceCreate"];

export type Command = Schemas["CommandOut"];
export type CommandStatus = Command["status"];
export type CommandResult = NonNullable<Command["result"]>;
export type Approval = Schemas["ApprovalOut"];
export type AppNotification = Schemas["NotificationOut"];
export type NotificationList = Schemas["NotificationList"];
export type Extraction = Schemas["ExtractionOut"];

// Phase 4: inbox, automation, approved answers, developer tools.
export type Conversation = Schemas["ConversationOut"];
export type ConversationDetail = Schemas["ConversationDetailOut"];
export type ChatMessage = Schemas["MessageOut"];
export type ReplyDraft = Schemas["ReplyDraftOut"];
export type ReplyWithWarnings = Schemas["ReplyWithWarningsOut"];
export type ValidationIssue = Schemas["ValidationIssueOut"];
export type ApprovedAnswer = Schemas["ApprovedAnswerOut"];
export type AutomationPolicies = Schemas["PoliciesOut"];
export type PolicyItem = Schemas["PolicyItem"];
export type SocialAccount = Schemas["SocialAccountOut"];
export type DevScript = Schemas["ScriptOut"];
export type FailureRule = Schemas["FailureRuleOut"];
export type DevJob = Schemas["JobOut"];
export type SimPublishedMedia = Schemas["PublishedMediaOut"];

// Phase 5: content and media.
export type ContentItem = Schemas["ContentItemOut"];
export type ContentStatus = ContentItem["status"];
export type ContentType = ContentItem["content_type"];
export type ContentTab = "drafts" | "scheduled" | "published" | "problems";
export type ContentValidation = Schemas["ContentValidationOut"];
export type ContentIssue = Schemas["ContentIssueOut"];
export type ContentCheckItem = Schemas["ContentCheckItemOut"];
export type ContentOperation = Schemas["ContentOperationOut"];
export type ContentGeneration = Schemas["GenerationOut"];
export type ContentCreateBody = Schemas["ContentCreate"];
export type ContentPatchBody = Schemas["ContentPatch"];
export type MediaAsset = Schemas["MediaAssetOut"];

// Phase 6: activity feed and the daily report.
export type ActivityEntry = Schemas["ActivityEntryOut"];
export type ActivityPage = Schemas["Page_ActivityEntryOut_"];
export type DailyReport = Schemas["DailyReportOut"];
export type ReportMetric = Schemas["MetricOut"];
export type MetricItems = Schemas["MetricItemsOut"];
export type MetricItem = Schemas["MetricItemOut"];
