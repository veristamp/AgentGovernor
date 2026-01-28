import type { LanguageModel } from "ai";
import type { MCPClientManager } from "../core/mcp/manager";
import type { PolicyEngine } from "../core/policy/engine";
import type { RuntimeContext } from "../runtime/factory";
import type { RuntimeIdentity } from "../runtime/middleware";
import type { RuntimeDeps } from "./types";

export type { RuntimeDeps };

/**
 * Context Builder
 *
 * Builds RuntimeContext from components. This is the main entry point
 * for creating execution contexts.
 */
export interface ContextBuilder {
  build: (deps: RuntimeDeps) => RuntimeContext;
  withOverrides: (
    base: RuntimeContext,
    overrides: Partial<RuntimeContext>,
  ) => RuntimeContext;
}

/**
 * Default context builder implementation
 */
export class StandardContextBuilder implements ContextBuilder {
  build(deps: RuntimeDeps): RuntimeContext {
    return {
      identity: deps.identity,
      mcp: deps.mcp,
      policy: deps.policy,
      model: deps.model,
    };
  }

  withOverrides(
    base: RuntimeContext,
    overrides: Partial<RuntimeContext>,
  ): RuntimeContext {
    return {
      ...base,
      ...overrides,
    };
  }
}

/**
 * Create a default context builder
 */
export function createContextBuilder(): ContextBuilder {
  return new StandardContextBuilder();
}

/**
 * Convenience function to build a context
 */
export function buildRuntimeContext(deps: RuntimeDeps): RuntimeContext {
  const builder = createContextBuilder();
  return builder.build(deps);
}