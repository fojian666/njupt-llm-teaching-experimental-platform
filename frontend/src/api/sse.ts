import { fetchEventSource } from '@microsoft/fetch-event-source'

export interface ChatEventHandlers {
  onStart?: (d: { conversation_id: number; model: string }) => void
  onRetrieval?: (d: { count: number; vector_count: number; lexical_count: number; note: string }) => void
  onCitations?: (d: { items: unknown[]; cited: number[] }) => void
  onReasoning?: (d: { text: string }) => void
  onDelta?: (d: { text: string }) => void
  onNotice?: (d: { message: string }) => void
  onError?: (d: { message: string }) => void
  onDone?: (d: Record<string, unknown>) => void
}

/**
 * 流式问答。用 fetch-event-source 而不是原生 EventSource：
 * 原生只支持 GET，而问答要 POST 一个带参数的 body。
 *
 * 注意中断语义：调用方拿到 abort 函数，用户点「停止生成」时触发，
 * 后端在 GeneratorExit 里会把已生成的半截回答存下来，不会丢。
 */
export async function streamChat(
  agentId: number,
  payload: Record<string, unknown>,
  handlers: ChatEventHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await fetchEventSource(`/api/agents/${agentId}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
    signal,
    credentials: 'include',
    openWhenHidden: true, // 切到别的标签页时不要断流

    onmessage(ev) {
      let data: Record<string, unknown> = {}
      try {
        data = ev.data ? JSON.parse(ev.data) : {}
      } catch {
        return
      }
      switch (ev.event) {
        case 'start':
          handlers.onStart?.(data as never)
          break
        case 'retrieval':
          handlers.onRetrieval?.(data as never)
          break
        case 'citations':
          handlers.onCitations?.(data as never)
          break
        case 'reasoning':
          handlers.onReasoning?.(data as never)
          break
        case 'delta':
          handlers.onDelta?.(data as never)
          break
        case 'notice':
          handlers.onNotice?.(data as never)
          break
        case 'error':
          handlers.onError?.(data as never)
          break
        case 'done':
          handlers.onDone?.(data as never)
          break
      }
    },

    onerror(err) {
      // 抛出去让调用方知道流断了；返回 false 表示不要自动重连
      handlers.onError?.({ message: `连接中断：${err?.message ?? err}` })
      throw err
    },
  })
}
