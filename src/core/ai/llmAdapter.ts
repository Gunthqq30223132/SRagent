import type { PatientData } from '@/types/medical'

export interface LLMMessage {
  role: 'user' | 'assistant' | 'system'
  content: string
}

export interface MedicalContext {
  patient?: PatientData
  activeCalculator?: string
  recentResults?: Record<string, number | string>
}

export interface LLMStreamEvent {
  type: 'delta' | 'done' | 'error'
  content?: string
  error?: string
}

// Adapter interface — cắm bất kỳ LLM nào (Claude, OpenAI, ...) mà không thay đổi UI
export interface LLMAdapter {
  readonly name: string
  readonly isAvailable: boolean

  chat(
    messages: LLMMessage[],
    context: MedicalContext,
    signal: AbortSignal,
  ): AsyncIterable<LLMStreamEvent>

  getSuggestedPrompts(context: MedicalContext): string[]
}

// Phase 1: NullAdapter — trả về trạng thái "chưa khả dụng"
export class NullLLMAdapter implements LLMAdapter {
  readonly name = 'null'
  readonly isAvailable = false

  async *chat(): AsyncIterable<LLMStreamEvent> {
    yield { type: 'error', error: 'AI chưa được kích hoạt trong phiên bản này.' }
  }

  getSuggestedPrompts(): string[] {
    return []
  }
}

export const defaultAdapter: LLMAdapter = new NullLLMAdapter()
