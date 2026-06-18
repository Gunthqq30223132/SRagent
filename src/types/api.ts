export interface ApiResponse<T> {
  data: T
  ok: boolean
  error?: string
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  total: number
  page: number
  limit: number
}

// Network status aware fetch options
export interface FetchOptions extends RequestInit {
  timeout?: number
  offlineFallback?: () => unknown
}
