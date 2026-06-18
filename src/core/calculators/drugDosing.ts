import type { DoseResult, PatientData, Drug } from '@/types/medical'

// ─── Hằng số liều thuốc khởi mê ─────────────────────────────────────────────
// Nguồn: Miller's Anesthesia, 9th ed. + Dược thư Quốc gia Việt Nam 2022

const INDUCTION_DRUGS = {
  propofol: {
    nameGeneric: 'Propofol',
    nameVn: 'Propofol',
    brandNamesVn: ['Diprivan', 'Propofol Fresenius', 'Recofol'],
    concentration: '10mg/mL (1%)',
    minMgPerKg: 1.0,
    maxMgPerKg: 2.5,
    // Giảm liều ở người già (>55 tuổi) và ASA III/IV
    elderlyReductionFactor: 0.6,
    elderlyAgeThreshold: 55,
    notes: [
      'Tiêm chậm 20-40 giây để giảm đau tại chỗ tiêm',
      'Giảm liều 30-40% ở bệnh nhân cao tuổi hoặc ASA III/IV',
      'Apnea thường gặp — chuẩn bị phương tiện hỗ trợ hô hấp',
    ],
  },
  ketamine: {
    nameGeneric: 'Ketamine',
    nameVn: 'Ketamin',
    brandNamesVn: ['Ketalar', 'Ketamine HCl'],
    concentration: '50mg/mL',
    minMgPerKg: 1.0,
    maxMgPerKg: 2.0,
    imMinMgPerKg: 4.0,
    imMaxMgPerKg: 8.0,
    notes: [
      'Tăng huyết áp và nhịp tim — thận trọng bệnh tim mạch',
      'Không ức chế hô hấp — an toàn hơn nơi thiếu nguồn lực',
      'Nên phối hợp Midazolam để giảm ác mộng',
      'Chống chỉ định: THA không kiểm soát, bệnh mạch vành nặng, tăng áp nội sọ',
    ],
  },
  etomidate: {
    nameGeneric: 'Etomidate',
    nameVn: 'Etomidate',
    brandNamesVn: ['Hypnomidate', 'Etomidate Lipuro'],
    concentration: '2mg/mL',
    minMgPerKg: 0.2,
    maxMgPerKg: 0.4,
    notes: [
      'Huyết động ổn định — ưu tiên bệnh nhân shock, bệnh tim',
      'Ức chế vỏ thượng thận sau liều đơn — tránh dùng kéo dài',
      'Đau tại chỗ tiêm và giật cơ là thường gặp',
    ],
  },
  thiopental: {
    nameGeneric: 'Thiopental Sodium',
    nameVn: 'Thiopental natri',
    brandNamesVn: ['Pentothal'],
    concentration: '25mg/mL (2.5%)',
    minMgPerKg: 3.0,
    maxMgPerKg: 5.0,
    notes: [
      'Giảm áp nội sọ — ưu tiên phẫu thuật thần kinh',
      'Hạ huyết áp và ức chế cơ tim đáng kể',
      'Chống chỉ định tuyệt đối: porphyria',
    ],
  },
} as const

type InductionDrugKey = keyof typeof INDUCTION_DRUGS

export interface InductionInput {
  drug: InductionDrugKey
  patient: PatientData
  useIm?: boolean  // tiêm bắp (chỉ Ketamine)
}

export function calculateInductionDose(input: InductionInput): DoseResult {
  const { drug, patient, useIm = false } = input
  const config = INDUCTION_DRUGS[drug]
  const { weightKg, ageYears = 40, asaScore } = patient

  let minPerKg: number = config.minMgPerKg
  let maxPerKg: number = config.maxMgPerKg

  // Ketamine IM
  if (drug === 'ketamine' && useIm) {
    const km = INDUCTION_DRUGS.ketamine
    minPerKg = km.imMinMgPerKg
    maxPerKg = km.imMaxMgPerKg
  }

  // Giảm liều người cao tuổi (Propofol)
  if (drug === 'propofol' && ageYears >= INDUCTION_DRUGS.propofol.elderlyAgeThreshold) {
    const factor = INDUCTION_DRUGS.propofol.elderlyReductionFactor
    minPerKg *= factor
    maxPerKg *= factor
  }

  // Giảm liều ASA III/IV (Propofol, Etomidate)
  if ((asaScore === 'III' || asaScore === 'IV') && drug !== 'ketamine') {
    minPerKg *= 0.7
    maxPerKg *= 0.7
  }

  const minDoseMg = Math.round(minPerKg * weightKg * 10) / 10
  const maxDoseMg = Math.round(maxPerKg * weightKg * 10) / 10
  const recommendedDoseMg = Math.round(((minDoseMg + maxDoseMg) / 2) * 10) / 10

  // Tính thể tích nếu biết nồng độ
  const concMatch = config.concentration.match(/(\d+)mg\/mL/)
  const concMgPerMl = concMatch ? Number(concMatch[1]) : undefined
  const volumeMl = concMgPerMl
    ? Math.round((recommendedDoseMg / concMgPerMl) * 10) / 10
    : undefined

  const isOverdose = recommendedDoseMg > maxPerKg * weightKg * 1.2

  return {
    drugName: config.nameGeneric,
    drugNameVn: config.nameVn,
    minDoseMg,
    maxDoseMg,
    recommendedDoseMg,
    volumeMl,
    concentration: config.concentration,
    route: useIm ? 'IM' : 'IV',
    notes: [...config.notes],
    isOverdose,
  }
}

// ─── Giãn cơ ─────────────────────────────────────────────────────────────────

const NMB_DRUGS = {
  rocuronium: {
    nameGeneric: 'Rocuronium bromide',
    nameVn: 'Rocuronium bromide',
    brandNamesVn: ['Esmeron', 'Rocuronium B.Braun'],
    concentration: '10mg/mL',
    intubatingMin: 0.6,
    intubatingMax: 1.2,      // RSI dose
    maintenanceMin: 0.1,
    maintenanceMax: 0.2,
    onset: '60-90 giây (0.6mg/kg) / 45-60 giây (1.2mg/kg)',
    duration: '30-60 phút',
    notes: [
      'RSI: dùng 1.2mg/kg để đặt NKQ trong 45-60 giây',
      'Đảo ngược bằng Sugammadex: 2mg/kg (TOF ≥2) hoặc 16mg/kg (RSI)',
      'Tích lũy trong suy thận/gan — giám sát neuromuscular monitoring',
    ],
  },
  vecuronium: {
    nameGeneric: 'Vecuronium bromide',
    nameVn: 'Vecuronium bromide',
    brandNamesVn: ['Norcuron'],
    concentration: '1mg/mL (sau pha)',
    intubatingMin: 0.08,
    intubatingMax: 0.12,
    maintenanceMin: 0.01,
    maintenanceMax: 0.02,
    onset: '3-5 phút',
    duration: '25-40 phút',
    notes: [
      'Pha với NaCl 0.9% hoặc Glucose 5% để đạt 1mg/mL',
      'Đảo ngược: Neostigmine 0.04mg/kg + Atropine 0.02mg/kg',
    ],
  },
  succinylcholine: {
    nameGeneric: 'Succinylcholine chloride',
    nameVn: 'Suxamethonium clorid',
    brandNamesVn: ['Succinylcholine', 'Anectine'],
    concentration: '20mg/mL',
    intubatingMin: 1.0,
    intubatingMax: 1.5,
    maintenanceMin: 0,
    maintenanceMax: 0,  // Không dùng để duy trì
    onset: '30-60 giây',
    duration: '8-12 phút',
    notes: [
      'Chỉ định RSI: khởi phát nhanh nhất (30-60 giây)',
      'CHỐNG CHỈ ĐỊNH: tăng Kali máu, tiền sử sốt ác tính (malignant hyperthermia), bỏng nặng, chấn thương nghiền nát',
      'Fasciculation (co cơ toàn thân) thường xảy ra trước khi liệt',
      'Không có thuốc đảo ngược đặc hiệu — thời gian tác dụng ngắn',
    ],
  },
  atracurium: {
    nameGeneric: 'Atracurium besylate',
    nameVn: 'Atracurium besylat',
    brandNamesVn: ['Tracrium'],
    concentration: '10mg/mL',
    intubatingMin: 0.4,
    intubatingMax: 0.5,
    maintenanceMin: 0.08,
    maintenanceMax: 0.1,
    onset: '2-3 phút',
    duration: '25-35 phút',
    notes: [
      'An toàn trong suy thận/gan — đào thải theo đường Hofmann',
      'Giải phóng histamine — tiêm chậm, tránh liều cao nhanh',
      'Ưu tiên bệnh nhân suy thận, suy gan nặng',
    ],
  },
} as const

type NmbDrugKey = keyof typeof NMB_DRUGS

export interface NmbInput {
  drug: NmbDrugKey
  patient: PatientData
  purpose: 'intubation' | 'maintenance'
  isRsi?: boolean  // Rapid Sequence Intubation
}

export function calculateNmbDose(input: NmbInput): DoseResult {
  const { drug, patient, purpose, isRsi = false } = input
  const config = NMB_DRUGS[drug]
  const { weightKg } = patient

  let minPerKg: number
  let maxPerKg: number

  if (purpose === 'maintenance') {
    minPerKg = config.maintenanceMin
    maxPerKg = config.maintenanceMax
  } else {
    minPerKg = config.intubatingMin
    maxPerKg = isRsi && drug === 'rocuronium' ? 1.2 : config.intubatingMax
  }

  const minDoseMg = Math.round(minPerKg * weightKg * 10) / 10
  const maxDoseMg = Math.round(maxPerKg * weightKg * 10) / 10
  const recommendedDoseMg = Math.round(((minDoseMg + maxDoseMg) / 2) * 10) / 10

  const concMatch = config.concentration.match(/(\d+)mg\/mL/)
  const concMgPerMl = concMatch ? Number(concMatch[1]) : undefined
  const volumeMl = concMgPerMl
    ? Math.round((recommendedDoseMg / concMgPerMl) * 10) / 10
    : undefined

  return {
    drugName: config.nameGeneric,
    drugNameVn: config.nameVn,
    minDoseMg,
    maxDoseMg,
    recommendedDoseMg,
    volumeMl,
    concentration: config.concentration,
    route: 'IV',
    notes: [...config.notes],
    isOverdose: false,
  }
}

// ─── Xuất kiểu Drug cho danh mục ─────────────────────────────────────────────

export type { Drug }
