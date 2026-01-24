export type AgentOutputFormat = 'python';

export interface AgentIdentityScope {
    orgId?: string;
    roles: string[];
    scopes: string[];
}

export interface AgentSkillSummary {
    skillRef: string;
    description: string;
    interfaces: string[];
    bindings: Record<string, string>;
    fanoutTools: string[];
}

export interface AgentSkillDetail extends AgentSkillSummary {}

export interface AgentWorkflowExample {
    id: string;
    goal: string;
    summary?: string;
    skills: string[];
}

export interface AgentPromptContext {
    skills: AgentSkillSummary[];
    selectedSkill?: AgentSkillDetail | null;
    workflowExamples?: AgentWorkflowExample[];
}

export interface AgentRequest {
    goal: string;
    identity: AgentIdentityScope;
    maxSkills?: number;
}

export interface AgentResult {
    code: string;
    selectedSkills: string[];
    prompt: string;
    repairAttempts: number;
}

export interface LlmMessage {
    role: 'system' | 'user' | 'assistant';
    content: string;
}

export interface LlmCompletionOptions {
    model: string;
    temperature?: number;
    maxTokens?: number;
    timeoutMs?: number;
}
