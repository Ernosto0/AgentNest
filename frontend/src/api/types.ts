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
