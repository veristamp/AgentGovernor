export interface SkillCreationRequest {
    goal: string;
    constraints?: string[];
    requester: {
        id: string;
        roles: string[];
        orgId?: string;
        teamId?: string;
    };
}

export interface ToolDescriptor {
    qualifiedName: string;
    serverPrefix: string;
    name: string;
    description: string;
    schema?: unknown;
}

export interface SkillDraft {
    skillId: string;
    version: number;
    summary: string;
    interfaces: string[];
    bindings: Record<string, string>;
    fanoutTools: string[];
    code: string;
}

export interface SkillCreatorOptions {
    model: string;
    temperature?: number;
    maxTokens?: number;
    maxRepairAttempts?: number;
    toolsPath?: string;
    skillsDir?: string;
    policyFilePath?: string;
    rolePermissionsPath?: string;
}

export interface AbacRuleProposal {
    id: string;
    action: string;
    conditions: {
        allowedOrgIds?: string[];
        allowedTeamIds?: string[];
    };
    priority: number;
}

export interface SkillCreationResult {
    skillRef: string;
    skillDir: string;
    draft: SkillDraft;
    rolesGranted: string[];
    orgsGranted: string[];
    teamsGranted: string[];
    abacProposal?: AbacRuleProposal;
}

export interface SkillCreatorSession {
    goal: string;
    constraints: string[];
    selectedTools: ToolDescriptor[];
    draft?: SkillDraft;
    questions: string[];
}

export type SkillCreatorEvent =
    | { type: 'question'; message: string }
    | { type: 'tool_selection'; tools: ToolDescriptor[] }
    | { type: 'draft'; draft: SkillDraft }
    | { type: 'complete'; result: SkillCreationResult };
