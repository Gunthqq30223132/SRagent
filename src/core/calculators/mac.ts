// Minimum Alveolar Concentration (MAC) Calculator
// Nguồn: Eger EI. Anesthetic Uptake and Action. Williams & Wilkins, 1974
// + Dripps Award Lecture, Anesthesiology 2002

// MAC cơ bản ở 37°C, áp suất 1 atm, người lớn 40 tuổi
const BASE_MAC: Record<string, number> = {
  sevoflurane:  2.0,   // %
  desflurane:   6.0,   // %
  isoflurane:   1.15,  // %
  halothane:    0.75,  // % (ít dùng, vẫn có tại một số BV VN)
  nitrous_oxide: 104,  // % (cần áp suất > 1 atm)
}

// Yếu tố hiệu chỉnh MAC theo tuổi
// MAC giảm ~6%/thập niên sau 40 tuổi
function ageCorrectionFactor(ageYears: number): number {
  if (ageYears < 1) return 1.6    // Trẻ sơ sinh cao hơn người lớn
  if (ageYears < 6) return 1.3
  if (ageYears < 16) return 1.1
  if (ageYears < 40) return 1.0
  return Math.max(0.4, 1.0 - 0.06 * ((ageYears - 40) / 10))
}

export interface MACInput {
  agent: keyof typeof BASE_MAC
  ageYears: number
  n2oPercent?: number    // Nồng độ N2O phối hợp (%)
  targetMacFraction?: number  // Mục tiêu (mặc định 1.0 MAC)
}

export interface MACResult {
  baseMac: number
  ageCorrectedMac: number
  n2oEquivalent: number       // MAC do N2O đóng góp
  remainingMac: number        // MAC cần từ thuốc bốc hơi
  targetConcentration: number // Nồng độ % cần đặt trên máy
  unit: '%'
  ageFactor: number
  notes: string[]
}

export function calculateMAC(input: MACInput): MACResult {
  const { agent, ageYears, n2oPercent = 0, targetMacFraction = 1.0 } = input

  const baseMac = BASE_MAC[agent] ?? 0
  const ageFactor = ageCorrectionFactor(ageYears)
  const ageCorrectedMac = Math.round(baseMac * ageFactor * 100) / 100

  // MAC do N2O đóng góp (tương đương phân số)
  const n2oEquivalent = Math.round((n2oPercent / BASE_MAC.nitrous_oxide) * 100) / 100
  const remainingMac = Math.max(0, targetMacFraction - n2oEquivalent)

  // Nồng độ % cần đặt trên máy
  const targetConcentration = Math.round(remainingMac * ageCorrectedMac * 100) / 100

  const notes: string[] = []
  if (n2oPercent > 70) notes.push('N2O > 70% — nguy cơ thiếu oxy. Duy trì FiO2 ≥ 30%')
  if (agent === 'halothane') notes.push('Halothane: nhạy cảm với catecholamine, nguy cơ loạn nhịp')
  if (ageYears > 70) notes.push('Người cao tuổi: MAC giảm đáng kể, tránh quá liều')
  if (targetConcentration > ageCorrectedMac * 1.5) {
    notes.push('⚠️ Nồng độ đặt cao — kiểm tra lại mục tiêu MAC')
  }

  return {
    baseMac,
    ageCorrectedMac,
    n2oEquivalent,
    remainingMac,
    targetConcentration,
    unit: '%',
    ageFactor: Math.round(ageFactor * 100) / 100,
    notes,
  }
}
