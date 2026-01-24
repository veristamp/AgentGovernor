import { PolicyEngine } from '../policy/engine';
import type { AgentRequest, AgentResult, AgentSkillDetail, AgentSkillSummary, AgentPromptContext, LlmCompletionOptions } from './types';
import { SkillCatalog } from './skill_catalog';
import { LlmClient } from './llm_client';
import { buildPrompt, buildRepairPrompt } from './prompt_builder';
import { analyzeCode } from '../audit';
import { WorkflowRegistry } from '../workflow_registry';

export interface AgentOptions {
    llm: LlmClient;
    policy: PolicyEngine;
    model: string;
    temperature?: number;
    maxTokens?: number;
    maxRepairAttempts?: number;
    workflowRegistry?: WorkflowRegistry;
}

class AgentValidationError extends Error {
    constructor(
        message: string,
        public code: string,
        public errors: string[],
        public attempts: number
    ) {
        super(message);
    }
}

export class Agent {
    private catalog: SkillCatalog;
    private workflows: WorkflowRegistry;

    constructor(private options: AgentOptions) {
        this.catalog = new SkillCatalog(options.policy);
        this.workflows = options.workflowRegistry ?? new WorkflowRegistry();
    }

    async run(request: AgentRequest): Promise<AgentResult> {
        this.catalog.refresh();

        const maxSkills = request.maxSkills ?? 5;
        const allowedSkills = this.catalog.listAllowed(request.identity, 200);
        let discovered = this.catalog.search(request.goal, request.identity, maxSkills);
        if (!discovered.length) {
            discovered = allowedSkills.slice(0, maxSkills);
        }

        const initialContext = this.buildContext(discovered, request.identity, request.goal);
        let prompt = buildPrompt(request.goal, initialContext);
        let totalAttempts = 0;

        try {
            const { code, attempts, manifest } = await this.callLlm(prompt, request.goal, initialContext);
            totalAttempts += attempts;
            if (manifest) {
                this.workflows.saveWorkflow(request.goal, code, manifest, {
                    id: request.identity.roles.join(','),
                    orgId: request.identity.orgId,
                });
            }
            return {
                code,
                selectedSkills: initialContext.skills.map((skill: AgentSkillSummary) => skill.skillRef),
                prompt: `${prompt.system}\n\n${prompt.user}`,
                repairAttempts: totalAttempts,
            };
        } catch (error) {
            if (!(error instanceof AgentValidationError)) {
                throw error;
            }

            totalAttempts += error.attempts;
            const shouldExpand = this.shouldExpandContext(error.errors, initialContext, allowedSkills);
            if (!shouldExpand) {
                throw error;
            }

            const expandedSkills = this.prioritizeSkills(allowedSkills, error.errors);
            const expandedContext = this.buildContext(expandedSkills, request.identity, request.goal);
            prompt = buildPrompt(request.goal, expandedContext);

            const { code, attempts, manifest } = await this.callLlm(prompt, request.goal, expandedContext);
            totalAttempts += attempts;
            if (manifest) {
                this.workflows.saveWorkflow(request.goal, code, manifest, {
                    id: request.identity.roles.join(','),
                    orgId: request.identity.orgId,
                });
            }

            return {
                code,
                selectedSkills: expandedContext.skills.map((skill: AgentSkillSummary) => skill.skillRef),
                prompt: `${prompt.system}\n\n${prompt.user}`,
                repairAttempts: totalAttempts,
            };
        }
    }

    private buildContext(
        skills: AgentSkillSummary[],
        identity: AgentRequest['identity'],
        goal: string
    ): AgentPromptContext {
        const selected = this.selectSkill(skills, identity);
        const workflowExamples = this.findWorkflowExamples(goal, skills, identity);
        return {
            skills,
            selectedSkill: selected,
            workflowExamples,
        };
    }

    private selectSkill(
        skills: AgentSkillSummary[],
        identity: AgentRequest['identity']
    ): AgentSkillDetail | null {
        if (!skills.length) return null;
        const chosen = skills[0];
        if (!chosen) return null;
        return this.catalog.inspect(chosen.skillRef, identity);
    }

    private findWorkflowExamples(
        goal: string,
        skills: AgentSkillSummary[],
        identity: AgentRequest['identity']
    ): AgentPromptContext['workflowExamples'] {
        const allowedSkills = skills.map((skill) => skill.skillRef);
        const results = this.workflows.search(goal, allowedSkills, identity.orgId, 3);
        return results.map((entry) => ({
            id: entry.metadata.id,
            goal: entry.metadata.goal,
            summary: entry.metadata.summary,
            skills: entry.metadata.skills,
        }));
    }

    private shouldExpandContext(
        errors: string[],
        context: AgentPromptContext,
        allowedSkills: AgentSkillSummary[]
    ): boolean {
        if (!allowedSkills.length) return false;
        if (context.skills.length >= allowedSkills.length) return false;

        return errors.some((error) =>
            error.toLowerCase().includes('not allowed by current context') ||
            error.toLowerCase().includes('skill manifest not found') ||
            error.toLowerCase().includes('no tool interfaces are available') ||
            error.toLowerCase().includes('no recognized skills found')
        );
    }

    private prioritizeSkills(
        allowedSkills: AgentSkillSummary[],
        errors: string[]
    ): AgentSkillSummary[] {
        const mentions = errors
            .map((error) => error.match(/skills:([\w-]+)@/i)?.[1])
            .filter((name): name is string => Boolean(name));

        if (!mentions.length) {
            return allowedSkills;
        }

        const preferred = allowedSkills.filter((skill) => {
            const match = skill.skillRef.match(/^skills:([^@]+)@/i)?.[1];
            return match ? mentions.includes(match) : false;
        });

        if (!preferred.length) {
            return allowedSkills;
        }

        const remainder = allowedSkills.filter((skill) => !preferred.includes(skill));
        return [...preferred, ...remainder];
    }

    private async callLlm(
        prompt: { system: string; user: string },
        goal: string,
        context: AgentPromptContext
    ): Promise<{ code: string; attempts: number; manifest?: { skills: string[]; tools: string[]; io_calls?: string[] } }> {
        const messages: Array<{ role: 'system' | 'user'; content: string }> = [
            { role: 'system', content: prompt.system },
            { role: 'user', content: prompt.user },
        ];

        const options: LlmCompletionOptions = {
            model: this.options.model,
            temperature: this.options.temperature ?? 0.2,
            maxTokens: this.options.maxTokens ?? 2048,
        };

        const maxAttempts = this.options.maxRepairAttempts ?? 2;
        let lastCode = '';
        let lastValidationErrors: string[] = [];

        for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
            const raw = await this.options.llm.complete([...messages], options);
            const code = this.extractCode(raw, goal);
            lastCode = code;

            const validation = await this.validateCode(code, context);
            lastValidationErrors = validation.errors;
            if (validation.valid) {
                return { code, attempts: attempt + 1, manifest: validation.manifest };
            }

            const repairPrompt = buildRepairPrompt(goal, context, code, validation.errors);
            messages.splice(0, messages.length, { role: 'system', content: repairPrompt.system }, { role: 'user', content: repairPrompt.user });
        }

        throw new AgentValidationError('LLM output failed validation after repair attempts.', lastCode, lastValidationErrors, maxAttempts);
    }

    private extractCode(response: string, goal: string): string {
        const fenceMatch = response.match(/```python\s*([\s\S]*?)```/i);
        if (fenceMatch?.[1]) {
            return fenceMatch[1].trim();
        }
        const looseMatch = response.match(/```\s*([\s\S]*?)```/);
        if (looseMatch?.[1]) {
            return looseMatch[1].trim();
        }
        if (response.includes('async def main')) {
            return response.trim();
        }
        throw new Error(`LLM output did not include python code for goal: ${goal}`);
    }

    private async validateCode(
        code: string,
        context: AgentPromptContext
    ): Promise<{ valid: boolean; errors: string[]; manifest?: { skills: string[]; tools: string[]; io_calls?: string[] } }> {
        const manifest = await analyzeCode(code);
        const errors = [...manifest.errors];

        const allowedSkills = new Set(context.skills.map((skill) => skill.skillRef));
        if (allowedSkills.size) {
            for (const skill of manifest.skills) {
                if (!allowedSkills.has(skill)) {
                    errors.push(`Skill '${skill}' not allowed by current context`);
                }
            }
        } else if (manifest.skills.length) {
            errors.push('No skills are available in the current context');
        }

        if (!manifest.skills.length && manifest.tools.length) {
            errors.push('No recognized skills found in code');
        }

        const allowedSkillCalls = new Set(
            context.skills.flatMap((skill) => {
                const skillId = skill.skillRef.match(/^skills:([^@]+)@/i)?.[1];
                if (!skillId) return [];
                return skill.interfaces
                    .map((signature) => signature.replace(/`/g, '').trim())
                    .map((signature) => signature.split('(')[0]?.trim())
                    .flatMap((method) => {
                        if (!method) return [];
                        if (method.includes('.')) {
                            return [method];
                        }
                        return [`${skillId}.${method}`];
                    });
            })
        );

        if (allowedSkillCalls.size) {
            for (const call of manifest.tools) {
                if (!allowedSkillCalls.has(call)) {
                    errors.push(`Tool '${call}' not allowed by current context`);
                }
            }
        } else if (manifest.tools.length) {
            errors.push('No tool interfaces are available in the current context');
        }

        const hasAsyncMain = code.includes('async def main');
        if (!hasAsyncMain) {
            errors.push("Code must define 'async def main()'");
        }

        return { valid: errors.length === 0, errors, manifest };
    }
}
