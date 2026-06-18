import type { FluidResult } from '@/types/medical'

// Nguồn: Holliday-Segar formula, Miller's Anesthesia 9th ed.

export interface FluidInput {
  weightKg: number
  nilByMouthHours: number    // Số giờ nhịn ăn uống trước mổ
  surgeryDurationHours: number
  surgeryType: 'minor' | 'moderate' | 'major'
}

// Lượng dịch bù thiếu hụt do nhịn ăn (ml)
function calculateDeficit(weightKg: number, nilByMouthHours: number): number {
  const maintenance = calculateMaintenancePerHour(weightKg)
  // Bù 50% trong giờ đầu, 25% giờ 2, 25% giờ 3
  return maintenance * nilByMouthHours
}

// Nhu cầu dịch duy trì theo công thức 4-2-1 (ml/h)
function calculateMaintenancePerHour(weightKg: number): number {
  if (weightKg <= 10) return 4 * weightKg
  if (weightKg <= 20) return 40 + 2 * (weightKg - 10)
  return 60 + 1 * (weightKg - 20)
}

// Dịch mất trong mổ ước tính (ml/h) theo loại phẫu thuật
function calculateIntraopLossPerHour(weightKg: number, surgeryType: FluidInput['surgeryType']): number {
  const lossPerKgPerHour = { minor: 2, moderate: 4, major: 8 }
  return lossPerKgPerHour[surgeryType] * weightKg
}

export function calculateFluid(input: FluidInput): FluidResult {
  const { weightKg, nilByMouthHours, surgeryDurationHours, surgeryType } = input

  const maintenancePerHour = Math.round(calculateMaintenancePerHour(weightKg))
  const deficitTotal = Math.round(calculateDeficit(weightKg, nilByMouthHours))
  const intraopLossPerHour = calculateIntraopLossPerHour(weightKg, surgeryType)
  const intraopEstimate = Math.round(
    maintenancePerHour * surgeryDurationHours +
    deficitTotal +
    intraopLossPerHour * surgeryDurationHours,
  )

  return {
    maintenancePerHour,
    deficitReplacement: deficitTotal,
    intraopEstimate,
    recommendedFluid: weightKg < 3
      ? 'Dextrose 5% + NaCl 0.45% (trẻ sơ sinh)'
      : 'Lactated Ringer\'s (Ringer Lactat) / NaCl 0.9%',
  }
}

// Công thức bù dịch chiến lược 4-2-1 trực quan
export function getFluidStrategy(
  totalMl: number,
  surgeryDurationHours: number,
): { hour1: number; hour2: number; hourly: number } {
  // Bù 50% trong giờ đầu
  const hour1 = Math.round(totalMl * 0.5)
  // 25% giờ 2
  const hour2 = Math.round(totalMl * 0.25)
  // 25% còn lại chia đều các giờ sau
  const remaining = totalMl - hour1 - hour2
  const hoursLeft = Math.max(surgeryDurationHours - 2, 1)
  const hourly = Math.round(remaining / hoursLeft)

  return { hour1, hour2, hourly }
}
