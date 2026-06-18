// Dữ liệu bệnh nhân cơ bản cho một ca tính toán
export interface PatientData {
  weightKg: number
  ageYears: number
  heightCm?: number
  sex?: 'male' | 'female'
  asaScore?: ASAClass
  allergies?: string[]
}

// ASA Physical Status Classification
export type ASAClass = 'I' | 'II' | 'III' | 'IV' | 'V' | 'VI'

export interface ASACriteria {
  class: ASAClass
  label: string        // Tiếng Việt
  description: string  // Mô tả tiếng Việt
  examples: string[]
  emergencySuffix: boolean  // Thêm "E" nếu cấp cứu
}

// Kết quả tính liều thuốc
export interface DoseResult {
  drugName: string
  drugNameVn: string      // Tên tiếng Việt / biệt dược VN
  minDoseMg: number
  maxDoseMg: number
  recommendedDoseMg: number
  volumeMl?: number       // Nếu biết nồng độ
  concentration?: string  // Ví dụ: "1% (10mg/mL)"
  route: RouteOfAdmin
  notes?: string[]        // Cảnh báo lâm sàng
  isOverdose?: boolean
}

export type RouteOfAdmin = 'IV' | 'IM' | 'SC' | 'PO' | 'Inhalation' | 'Epidural' | 'Spinal'

// Thuốc trong danh mục
export interface Drug {
  id: string
  nameGeneric: string
  nameVn: string          // Tên tiếng Việt
  brandNamesVn: string[]  // Tên biệt dược tại VN
  category: DrugCategory
  minDoseMgPerKg: number
  maxDoseMgPerKg: number
  concentration: string   // Nồng độ thông dụng tại VN
  route: RouteOfAdmin[]
  onset: string           // "30-60 giây"
  duration: string        // "5-10 phút"
  contraindications: string[]
  interactions: string[]
  notes: string[]
}

export type DrugCategory =
  | 'induction'         // Thuốc khởi mê
  | 'maintenance'       // Thuốc duy trì mê
  | 'opioid'            // Giảm đau opioid
  | 'muscle-relaxant'   // Giãn cơ
  | 'reversal'          // Đảo ngược giãn cơ
  | 'local-anesthetic'  // Tê tại chỗ / vùng
  | 'sedation'          // An thần ICU
  | 'vasopressor'       // Vận mạch
  | 'emergency'         // Cấp cứu

// Kết quả tính thể tích dịch truyền
export interface FluidResult {
  maintenancePerHour: number    // mL/h theo 4-2-1
  deficitReplacement: number    // mL bù thiếu hụt (nếu nhịn ăn)
  intraopEstimate: number       // mL cho ca mổ (estimate)
  recommendedFluid: string      // "Lactated Ringer's / NaCl 0.9%"
}

// Lịch sử ca tính toán (lưu local, không có PHI)
export interface CalculationRecord {
  id: string
  timestamp: number
  toolUsed: string
  patientLabel: string  // "BN #1" — không lưu tên thật
  inputs: Record<string, number | string>
  results: Record<string, number | string>
}

// ─── Kế hoạch gây mê ─────────────────────────────────────────────────────────

export type AnaesthesiaType =
  | 'general'      // Gây mê toàn thân
  | 'neuraxial'    // Tê trục thần kinh (tủy sống / ngoài màng cứng)
  | 'regional'     // Tê vùng (block thần kinh ngoại biên)
  | 'local'        // Gây tê tại chỗ
  | 'mac'          // Monitored Anaesthesia Care (an thần có giám sát)
  | 'combined'     // Kết hợp (GA + regional)

export type AgeUnit = 'years' | 'months' | 'days'

export interface PlanPatientData extends PatientData {
  ageValue: number      // Số tuổi theo đơn vị bên dưới
  ageUnit: AgeUnit      // Đơn vị tuổi
  bmi?: number
  allergies: string[]
  currentMedications: string[]
}

export interface SelectedSurgery {
  specialtyId: string
  specialtyNameVn: string
  surgeryId: string
  surgeryNameVn: string
  surgeryNameEn: string
  recommendedAnaesthesia: AnaesthesiaType
  anaesthesiaOptions: AnaesthesiaType[]
  position: string
  durationMin: number
  durationMax: number
  urgency: 'elective' | 'urgent' | 'emergency'
  bloodLoss: 'minimal' | 'low' | 'moderate' | 'high' | 'massive'
  painLevel: 'mild' | 'moderate' | 'severe'
  airwayDifficulty: 'standard' | 'shared' | 'difficult' | 'secured'
  considerations: string[]
}

export interface SelectedComorbidity {
  categoryId: string
  categoryNameVn: string
  conditionId: string
  conditionNameVn: string
  conditionNameEn: string
  asaMinimum: ASAClass
  anaesthesiaConsiderations: string[]
  drugCautions: string[]
  monitoringNeeds: string[]
  preOpChecklist: string[]
}

// Đầu vào của trình tạo kế hoạch
export interface PlanInput {
  patient: PlanPatientData
  surgery: SelectedSurgery
  comorbidities: SelectedComorbidity[]
  isEmergency: boolean
  preferredAnaesthesia?: AnaesthesiaType  // bác sĩ có thể ghi đè
}

// Phần trong kế hoạch gây mê
export interface PlanSection {
  title: string
  items: string[]
  level?: 'info' | 'caution' | 'danger'  // highlight màu nếu cần
}

// Kế hoạch gây mê được tạo ra (rule-based Phase 1, LLM Phase 2)
export interface GeneratedPlan {
  anaesthesiaType: AnaesthesiaType
  anaesthesiaTypeLabel: string
  asaClass: ASAClass
  sections: PlanSection[]
  warnings: string[]       // cảnh báo đặc biệt (màu đỏ)
  generatedAt: number      // timestamp
  isAiGenerated: boolean   // false ở Phase 1
}

// Kế hoạch đã lưu (My Plans)
export interface SavedPlan {
  id: string
  label: string            // "BN #1 — Cắt ruột thừa" — không lưu tên thật
  createdAt: number
  surgeryNameVn: string
  anaesthesiaType: AnaesthesiaType
  asaClass: ASAClass
  input: PlanInput
  plan: GeneratedPlan
}
