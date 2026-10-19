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
