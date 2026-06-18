import type { ASAClass, ASACriteria } from '@/types/medical'

// Nguồn: ASA Physical Status Classification System (ASA 2020 update)
// Được Hội Gây mê Hồi sức Việt Nam công nhận

export const ASA_CRITERIA: Record<ASAClass, ASACriteria> = {
  I: {
    class: 'I',
    label: 'ASA I — Bình thường, khỏe mạnh',
    description: 'Bệnh nhân khỏe mạnh, không hút thuốc, không uống rượu hoặc uống rất ít.',
    examples: [
      'Bệnh nhân khỏe mạnh hoàn toàn',
      'BMI < 30',
      'Không có bệnh lý mãn tính',
    ],
    emergencySuffix: false,
  },
  II: {
    class: 'II',
    label: 'ASA II — Bệnh hệ thống nhẹ',
    description: 'Bệnh hệ thống nhẹ, không ảnh hưởng chức năng.',
    examples: [
      'Đái tháo đường type 2 kiểm soát tốt',
      'THA kiểm soát tốt',
      'Hút thuốc, béo phì (BMI 30-40)',
      'Thai kỳ, thiếu máu nhẹ',
      'Tiền sử nhồi máu cơ tim, đột quỵ > 3 tháng, không triệu chứng',
    ],
    emergencySuffix: false,
  },
  III: {
    class: 'III',
    label: 'ASA III — Bệnh hệ thống nặng',
    description: 'Bệnh hệ thống nặng, giới hạn hoạt động nhưng không đe dọa tính mạng.',
    examples: [
      'ĐTĐ hoặc THA kiểm soát kém',
      'COPD nặng',
      'Tiền sử nhồi máu cơ tim, đột quỵ, TIA trong vòng 3 tháng',
      'Suy thận mãn (GFR < 60)',
      'BMI ≥ 40',
      'Nghiện rượu nặng hoặc lạm dụng ma túy đang hoạt động',
    ],
    emergencySuffix: false,
  },
  IV: {
    class: 'IV',
    label: 'ASA IV — Bệnh đe dọa tính mạng',
    description: 'Bệnh hệ thống nặng, đe dọa tính mạng thường xuyên.',
    examples: [
      'Nhồi máu cơ tim cấp hoặc mới (< 3 tháng)',
      'Suy tim sung huyết nặng (EF < 25%)',
      'Rối loạn nhịp tim đe dọa tính mạng',
      'Suy thận nặng (GFR < 15, đang lọc thận)',
      'Suy gan nặng (Child-Pugh C)',
      'Sepsis nặng',
    ],
    emergencySuffix: false,
  },
  V: {
    class: 'V',
    label: 'ASA V — Nguy kịch, không mổ khó sống qua 24h',
    description: 'Bệnh nhân hấp hối, không mổ thì không sống được.',
    examples: [
      'Vỡ phình động mạch chủ bụng',
      'Chấn thương sọ não nặng',
      'Tắc mạch ruột với suy tim/hệ thống nặng',
      'Suy đa tạng nặng',
    ],
    emergencySuffix: false,
  },
  VI: {
    class: 'VI',
    label: 'ASA VI — Chết não, hiến tạng',
    description: 'Bệnh nhân chết não, tiến hành phẫu thuật để lấy tạng.',
    examples: ['Bệnh nhân chết não chờ lấy tạng hiến'],
    emergencySuffix: false,
  },
}

export interface ASAInput {
  selectedCriteria: Partial<Record<ASAClass, boolean>>
  isEmergency: boolean
}

export interface ASAResult {
  class: ASAClass
  label: string
  emergencyLabel?: string
  perioperativeRisk: string
  mortalityRate: string
}

// Tính điểm ASA từ các tiêu chí đã chọn
export function calculateASAScore(input: ASAInput): ASAResult {
  const { selectedCriteria, isEmergency } = input

  // Lấy ASA cao nhất được chọn
  const classes: ASAClass[] = ['VI', 'V', 'IV', 'III', 'II', 'I']
  let finalClass: ASAClass = 'I'

  for (const cls of classes) {
    if (selectedCriteria[cls]) {
      finalClass = cls
      break
    }
  }

  const criteria = ASA_CRITERIA[finalClass]

  const riskMap: Record<ASAClass, { risk: string; mortality: string }> = {
    I:   { risk: 'Rất thấp',        mortality: '< 0.03%' },
    II:  { risk: 'Thấp',            mortality: '0.03-0.2%' },
    III: { risk: 'Trung bình',      mortality: '0.2-1.2%' },
    IV:  { risk: 'Cao',             mortality: '1.2-8%' },
    V:   { risk: 'Rất cao',         mortality: '> 8%' },
    VI:  { risk: 'N/A (chết não)',  mortality: 'N/A' },
  }

  const { risk, mortality } = riskMap[finalClass]

  return {
    class: finalClass,
    label: criteria.label,
    emergencyLabel: isEmergency ? `${finalClass}E — ${criteria.label} (CẤP CỨU)` : undefined,
    perioperativeRisk: risk,
    mortalityRate: mortality,
  }
}
