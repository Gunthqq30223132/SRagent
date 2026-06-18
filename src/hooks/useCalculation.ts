import { useState, useCallback } from 'react'

// Generic hook cho mọi pure calculation function
export function useCalculation<TInput, TResult>(
  fn: (input: TInput) => TResult,
) {
  const [result, setResult] = useState<TResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const calculate = useCallback(
    (input: TInput) => {
      try {
        setError(null)
        setResult(fn(input))
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Lỗi tính toán không xác định')
        setResult(null)
      }
    },
    [fn],
  )

  const reset = useCallback(() => {
    setResult(null)
    setError(null)
  }, [])

  return { result, error, calculate, reset }
}
