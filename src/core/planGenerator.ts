import type {
  PlanInput,
  GeneratedPlan,
  PlanSection,
  AnaesthesiaType,
  ASAClass,
  SelectedComorbidity,
} from '@/types/medical'
import { calculateInductionDose } from './calculators/drugDosing'
import { calculateNmbDose } from './calculators/drugDosing'

// ─── Helper ──────────────────────────────────────────────────────────────────

const ANAESTHESIA_LABEL: Record<AnaesthesiaType, string> = {
  general:   'Gây mê toàn thân (Nội khí quản / LMA)',
  neuraxial: 'Tê trục thần kinh (Tủy sống / Ngoài màng cứng)',
  regional:  'Tê vùng (Block thần kinh ngoại biên)',
  local:     'Gây tê tại chỗ',
  mac:       'Monitored Anaesthesia Care (An thần có giám sát)',
  combined:  'Kết hợp (Gây mê + Tê vùng)',
}

function resolveASAClass(comorbidities: SelectedComorbidity[]): ASAClass {
  const classOrder: ASAClass[] = ['VI', 'V', 'IV', 'III', 'II', 'I']
  let highest: ASAClass = 'I'
  for (const c of comorbidities) {
    const idx = classOrder.indexOf(c.asaMinimum)
    if (idx < classOrder.indexOf(highest)) {
      highest = c.asaMinimum
    }
  }
  return highest
}

function resolveAnaesthesiaType(input: PlanInput): AnaesthesiaType {
  if (input.preferredAnaesthesia) return input.preferredAnaesthesia

  const { surgery, comorbidities, isEmergency } = input

  // Cấp cứu với phẫu thuật bụng → ưu tiên GA
  if (isEmergency && surgery.bloodLoss !== 'minimal') return 'general'

  // Kiểm tra chống chỉ định tê trục thần kinh
  const hasCoagulationIssue = comorbidities.some(
    (c) =>
      c.drugCautions.some((d) =>
        d.toLowerCase().includes('kháng đông') || d.toLowerCase().includes('aspirin'),
      ) && c.categoryId === 'hematologic',
  )

  const surgeryType = surgery.recommendedAnaesthesia
  if (surgeryType === 'neuraxial' && hasCoagulationIssue) return 'general'

  return surgeryType
}

function buildPatientSummarySection(input: PlanInput, asaClass: ASAClass): PlanSection {
  const { patient } = input
  const bmi = patient.heightCm
    ? Math.round((patient.weightKg / ((patient.heightCm / 100) ** 2)) * 10) / 10
    : undefined

  const items: string[] = [
    `Giới tính: ${patient.sex === 'male' ? 'Nam' : 'Nữ'}`,
    `Tuổi: ${patient.ageValue} ${patient.ageUnit === 'years' ? 'tuổi' : patient.ageUnit === 'months' ? 'tháng' : 'ngày'}`,
    `Cân nặng: ${patient.weightKg} kg${patient.heightCm ? ` · Chiều cao: ${patient.heightCm} cm` : ''}`,
    ...(bmi ? [`BMI: ${bmi}${bmi >= 30 ? ' ⚠️ Béo phì' : bmi >= 40 ? ' ⚠️ Béo phì bệnh lý' : ''}`] : []),
    `Phân loại ASA: ${asaClass}${input.isEmergency ? 'E' : ''}`,
  ]

  if (patient.allergies.length > 0) {
    items.push(`Dị ứng: ${patient.allergies.join(', ')}`)
  }
  if (patient.currentMedications.length > 0) {
    items.push(`Thuốc đang dùng: ${patient.currentMedications.join(', ')}`)
  }

  return { title: 'Thông tin bệnh nhân', items }
}

function buildPreOpSection(input: PlanInput): PlanSection {
  const { comorbidities, surgery, patient } = input

  const items: string[] = []

  // Xét nghiệm cơ bản
  items.push('Xét nghiệm cơ bản: CBC, TS/TC (hoặc PT/INR/APTT), glucose, điện giải đồ, creatinine')

  // ECG theo tuổi/bệnh
  if (
    patient.ageYears >= 40 ||
    comorbidities.some((c) => c.categoryId === 'cardiovascular')
  ) {
    items.push('ECG 12 chuyển đạo (≥40 tuổi hoặc bệnh tim mạch)')
  }

  // XQ ngực
  if (
    comorbidities.some((c) => ['cardiovascular', 'respiratory'].includes(c.categoryId))
  ) {
    items.push('XQ phổi thẳng (bệnh tim/phổi)')
  }

  // Siêu âm tim
  if (comorbidities.some((c) =>
    c.conditionId.includes('heart-failure') ||
    c.conditionId.includes('valve') ||
    c.conditionId.includes('cabg'),
  )) {
    items.push('Siêu âm tim (đánh giá chức năng thất/EF trước mổ lớn)')
  }

  // Chức năng phổi
  if (comorbidities.some((c) => c.categoryId === 'respiratory')) {
    items.push('Chức năng hô hấp (spirometry) nếu COPD/hen phế quản')
  }

  // Bilan gan thận
  if (comorbidities.some((c) => ['hepatic', 'renal'].includes(c.categoryId))) {
    items.push('Chức năng gan (AST, ALT, bilirubin, albumin) và thận (creatinine, eGFR)')
  }

  // Nhóm máu
  if (['moderate', 'high', 'massive'].includes(surgery.bloodLoss)) {
    items.push('Định nhóm máu + cross-match (dự trù máu cho ca có nguy cơ mất máu cao)')
  }

  // Chống đông
  if (comorbidities.some((c) => c.categoryId === 'hematologic')) {
    items.push('Đánh giá rối loạn đông máu: PT, INR, APTT, tiểu cầu')
  }

  // Pre-op từ comorbidities
  for (const c of comorbidities) {
    for (const item of c.preOpChecklist) {
      if (!items.includes(item)) items.push(item)
    }
  }

  // Nhịn ăn
  items.push(
    input.isEmergency
      ? '⚠️ Cấp cứu: coi dạ dày đầy — chuẩn bị RSI, kháng acid nếu có thể'
      : 'Nhịn ăn: rắn ≥ 6h · lỏng trong ≥ 2h · sữa mẹ ≥ 4h (trẻ em)',
  )

  return {
    title: 'Đánh giá & Xét nghiệm tiền mê',
    items,
    level: input.isEmergency ? 'caution' : 'info',
  }
}

function buildPremedSection(input: PlanInput): PlanSection {
  const { comorbidities, patient, isEmergency } = input
  const items: string[] = []

  // Thuốc THA buổi sáng
  if (comorbidities.some((c) => c.categoryId === 'cardiovascular')) {
    items.push('Tiếp tục thuốc huyết áp buổi sáng với ngụm nước nhỏ (trừ ACEI/ARB nếu phẫu thuật lớn)')
  }

  // ĐTĐ — ngừng insulin/metformin
  if (comorbidities.some((c) => c.categoryId === 'endocrine')) {
    items.push('ĐTĐ: ngừng metformin 24-48h, điều chỉnh insulin — kiểm soát glucose 6-10 mmol/L trước mổ')
  }

  // Giảm lo âu (nếu cần)
  if (!isEmergency) {
    if (comorbidities.some((c) => c.categoryId === 'psychiatric') || patient.ageYears < 12) {
      items.push('Tiền mê giảm lo lắng: Midazolam 0.02-0.05 mg/kg IV (người lớn) hoặc Midazolam 0.3-0.5 mg/kg PO (trẻ em)')
    }
  }

  // Giảm acid dạ dày
  if (isEmergency || comorbidities.some((c) => c.conditionId === 'gerd')) {
    items.push('Kháng acid: Ranitidine 50mg IV hoặc Omeprazole 40mg IV trước mổ')
  }

  // Kháng sinh dự phòng
  items.push('Kháng sinh dự phòng: theo phác đồ bệnh viện (thường Cefazolin 1-2g IV trong 30-60 phút trước rạch da)')

  if (items.length === 0) items.push('Không cần tiền mê đặc biệt')

  return { title: 'Tiền mê & Chuẩn bị', items }
}

function buildInductionSection(input: PlanInput, anaesthesiaType: AnaesthesiaType): PlanSection {
  const { patient, surgery, comorbidities, isEmergency } = input
  const items: string[] = []

  const patientData = {
    weightKg: patient.weightKg,
    ageYears: patient.ageYears,
    asaScore: patient.asaScore,
  }

  const isMallampati = comorbidities.some(
    (c) => c.conditionId === 'difficult-airway' || surgery.airwayDifficulty === 'difficult',
  )
  const isRSI = isEmergency || surgery.airwayDifficulty === 'secured'

  if (anaesthesiaType === 'general') {
    // Mồi tĩnh mạch
    items.push('Mở đường truyền tĩnh mạch cỡ lớn (≥18G) · Monitoring: SpO₂, ECG, huyết áp không xâm lấn')
    items.push('Tiền oxy hóa (preoxygenation) 100% O₂ trong 3-5 phút · đạt EtO₂ > 90%')

    if (isMallampati) {
      items.push('⚠️ Đường thở khó dự kiến — chuẩn bị video laryngoscope, bougie, mask LMA dự phòng')
    }

    // Thuốc khởi mê
    const isCardiacSick = comorbidities.some(
      (c) => c.categoryId === 'cardiovascular' && ['III', 'IV'].includes(c.asaMinimum),
    )
    const isHemodynamicallyUnstable =
      surgery.bloodLoss === 'massive' || surgery.urgency === 'emergency'

    let inductionDrug: 'propofol' | 'ketamine' | 'etomidate' = 'propofol'
    if (isHemodynamicallyUnstable || isCardiacSick) inductionDrug = 'etomidate'
    else if (isEmergency && patient.ageYears < 12) inductionDrug = 'ketamine'

    const doseResult = calculateInductionDose({
      drug: inductionDrug,
      patient: patientData,
    })

    items.push(
      `Khởi mê: ${doseResult.drugNameVn} ${doseResult.minDoseMg}–${doseResult.maxDoseMg} mg (${doseResult.minDoseMg / patient.weightKg}–${doseResult.maxDoseMg / patient.weightKg} mg/kg) IV chậm`,
    )

    // Giãn cơ
    const nmbDrug = isRSI ? 'rocuronium' : 'rocuronium'
    const nmbResult = calculateNmbDose({
      drug: nmbDrug,
      patient: patientData,
      purpose: 'intubation',
      isRsi: isRSI,
    })

    if (isRSI) {
      items.push(
        `RSI — Succinylcholine 1.0–1.5 mg/kg IV HOẶC Rocuronium ${nmbResult.recommendedDoseMg} mg (1.2 mg/kg) IV — ấn sụn nhẫn (Sellick) trong khi khởi mê`,
      )
    } else {
      items.push(
        `Giãn cơ: Rocuronium ${nmbResult.minDoseMg}–${nmbResult.maxDoseMg} mg (0.6 mg/kg) IV · Chờ 90 giây trước đặt nội khí quản`,
      )
    }

    // Đặt NKQ / LMA
    if (surgery.position === 'prone' || surgery.airwayDifficulty === 'secured') {
      items.push('Đặt NKQ có bóng (cuffed ETT) — bắt buộc cho phẫu thuật tư thế sấp hoặc đường thở cần bảo vệ')
    } else {
      items.push('Đặt NKQ hoặc LMA tùy theo phẫu thuật và nguy cơ đường thở')
    }

    // Opioid khởi mê
    items.push('Fentanyl 1–2 mcg/kg IV (hoặc Sufentanil 0.1–0.2 mcg/kg) khi khởi mê để giảm đáp ứng đặt ống')

  } else if (anaesthesiaType === 'neuraxial') {
    items.push('Tư thế: ngồi hoặc nằm nghiêng · vô khuẩn nghiêm ngặt')
    items.push('Tê tủy sống (SAB): Bupivacaine 0.5% tỷ trọng cao 10–15 mg (2–3 mL) ± Fentanyl 25 mcg')
    items.push('Kiểm tra mức tê trước khi bắt đầu phẫu thuật (mục tiêu T10 cho mổ lấy thai, T4-6 cho bụng dưới)')
    items.push('Dự phòng tụt huyết áp: Ephedrine 5–10 mg IV hoặc Phenylephrine 50–100 mcg IV khi cần')

  } else if (anaesthesiaType === 'regional') {
    items.push('Xác định dây thần kinh cần block theo vùng phẫu thuật')
    items.push('Dùng máy siêu âm (ultrasound-guided) để tăng độ chính xác và an toàn')
    items.push('Thuốc tê: Ropivacaine 0.5–0.75% hoặc Bupivacaine 0.5% · liều theo vùng block')
    items.push('Dự trữ Intralipid 20% (200 mL) tại chỗ để xử trí ngộ độc thuốc tê toàn thân (LAST)')

  } else if (anaesthesiaType === 'mac') {
    items.push('Monitoring đầy đủ: SpO₂, ECG, huyết áp · Oxy qua canula mũi 2–4 L/phút')
    items.push('An thần: Midazolam 1–2 mg IV + Fentanyl 25–50 mcg IV tiêm chậm (chia nhỏ liều)')
    items.push('Propofol TCI (Target Controlled Infusion) 0.5–2 mcg/mL nếu có hoặc infusion 1–3 mg/kg/h')
    items.push('Luôn sẵn sàng chuyển sang gây mê toàn thân nếu bệnh nhân không hợp tác')
  }

  return { title: 'Khởi mê & Đặt đường thở', items }
}

function buildMaintenanceSection(
  input: PlanInput,
  anaesthesiaType: AnaesthesiaType,
): PlanSection {
  const { surgery, comorbidities } = input
  const items: string[] = []

  if (anaesthesiaType === 'general') {
    // Duy trì mê bốc hơi vs TIVA
    const isRenalFailure = comorbidities.some((c) => c.categoryId === 'renal')
    const isLiverFailure = comorbidities.some((c) => c.categoryId === 'hepatic')

    if (isRenalFailure || isLiverFailure) {
      items.push('TIVA (Total Intravenous Anaesthesia) ưu tiên khi suy thận/gan: Propofol 4–6 mg/kg/h + Remifentanil 0.1–0.3 mcg/kg/phút')
    } else {
      items.push('Duy trì mê: Sevoflurane 1.0–2.0 MAC trong O₂/Không khí (50:50) · theo dõi MAC liên tục')
    }

    // Giãn cơ duy trì
    items.push('Giãn cơ duy trì: Rocuronium 0.1–0.15 mg/kg IV PRN · theo dõi TOF nếu có')

    // Giảm đau trong mổ
    items.push('Giảm đau trong mổ: Fentanyl 0.5–1 mcg/kg IV PRN · hoặc Paracetamol 15 mg/kg IV infusion (truyền TM)')

    // Dịch truyền
    const isHighBloodLoss = ['high', 'massive'].includes(surgery.bloodLoss)
    if (isHighBloodLoss) {
      items.push('Dịch truyền: Lactated Ringer\'s 5–10 mL/kg/h trong mổ · Khi mất máu >500 mL: truyền máu theo TEG/ROTEM hoặc Hgb < 8 g/dL')
      items.push('Đặt đường truyền trung tâm (CVP) + huyết áp xâm lấn (IBP) cho ca mất máu nhiều')
    } else {
      items.push('Dịch truyền: Lactated Ringer\'s theo 4-2-1 mL/kg/h · bù thiếu hụt do nhịn ăn trong 1-2h đầu')
    }

    // Thở máy
    items.push('Thông khí bảo vệ phổi: TV 6–8 mL/kg IBW · PEEP 5 cmH₂O · RR để duy trì EtCO₂ 35–45 mmHg')

    // Theo dõi độ mê
    if (['high', 'massive'].includes(surgery.bloodLoss) || input.isEmergency) {
      items.push('Theo dõi độ sâu gây mê: BIS 40–60 (nếu có) để tránh awareness')
    }

  } else if (anaesthesiaType === 'neuraxial') {
    items.push('Kiểm tra mức tê và huyết động 5 phút/lần trong 30 phút đầu · sau đó 15 phút/lần')
    items.push('Bổ sung an thần nhẹ nếu phẫu thuật kéo dài: Midazolam 1–2 mg IV hoặc Propofol 1–2 mg/kg/h')
    items.push('Nếu tê tủy sống mờ sớm: cân nhắc chuyển sang gây mê toàn thân')

  } else if (anaesthesiaType === 'regional') {
    items.push('Theo dõi vùng block và vùng không block mỗi 15 phút')
    items.push('Bổ sung an thần: Midazolam 1–2 mg IV ± Fentanyl 25–50 mcg IV nếu bệnh nhân lo lắng')
  }

  return { title: 'Duy trì gây mê', items }
}

function buildMonitoringSection(
  input: PlanInput,
  anaesthesiaType: AnaesthesiaType,
): PlanSection {
  const { surgery, comorbidities, patient } = input
  const items: string[] = []

  // Monitoring cơ bản (mọi ca)
  items.push('Cơ bản (bắt buộc): SpO₂, ECG liên tục, huyết áp không xâm lấn, nhiệt độ, EtCO₂ (nếu có NKQ/LMA)')

  // Monitoring nâng cao
  const needsIBP =
    comorbidities.some((c) =>
      ['cardiovascular', 'renal'].includes(c.categoryId) && c.asaMinimum >= 'III',
    ) ||
    ['high', 'massive'].includes(surgery.bloodLoss) ||
    surgery.surgeryId.includes('cabg') ||
    surgery.surgeryId.includes('aortic')

  if (needsIBP) {
    items.push('Huyết áp xâm lấn (IBP — động mạch quay) cho ca có nguy cơ huyết động bất ổn')
  }

  const needsCVP =
    ['high', 'massive'].includes(surgery.bloodLoss) ||
    comorbidities.some((c) => c.categoryId === 'cardiovascular' && c.asaMinimum >= 'III')

  if (needsCVP) {
    items.push('Đường truyền trung tâm (CVP) — đặt trước khởi mê cho ca mất máu nhiều')
  }

  // Neuromuscular monitoring
  if (anaesthesiaType === 'general') {
    items.push('TOF (Train-of-Four) nếu dùng giãn cơ — đảm bảo TOF ratio ≥ 0.9 trước rút nội khí quản')
  }

  // BIS/Entropy
  if (
    ['high', 'massive'].includes(surgery.bloodLoss) ||
    patient.ageYears > 65 ||
    input.isEmergency
  ) {
    items.push('BIS/Entropy (theo dõi độ sâu mê) — đặc biệt bệnh nhân > 65 tuổi hoặc nguy cơ awareness')
  }

  // Nhiệt độ cơ thể
  if (surgery.durationMax > 90) {
    items.push('Theo dõi nhiệt độ lõi · chăn ấm/đệm nhiệt để tránh hạ thân nhiệt (< 36°C)')
  }

  // Nước tiểu
  if (surgery.durationMax > 120 || ['high', 'massive'].includes(surgery.bloodLoss)) {
    items.push('Đặt thông tiểu — theo dõi lượng nước tiểu (mục tiêu > 0.5 mL/kg/h)')
  }

  // Monitoring từ comorbidities
  for (const c of comorbidities) {
    for (const m of c.monitoringNeeds) {
      if (!items.some((i) => i.includes(m.substring(0, 20)))) {
        items.push(m)
      }
    }
  }

  return { title: 'Theo dõi trong mổ', items }
}

function buildEmergenceSection(
  input: PlanInput,
  anaesthesiaType: AnaesthesiaType,
): PlanSection {
  const { comorbidities, patient } = input
  const items: string[] = []

  if (anaesthesiaType === 'general') {
    items.push('Ngừng thuốc mê bốc hơi khi đóng vết mổ · đảm bảo TOF ratio ≥ 0.9 trước đảo ngược')

    const hasRenalIssue = comorbidities.some((c) => c.categoryId === 'renal')
    if (!hasRenalIssue) {
      items.push('Đảo ngược giãn cơ: Sugammadex 2 mg/kg IV (khi TOF ≥ 2) hoặc Neostigmine 0.04 mg/kg + Atropine 0.02 mg/kg IV')
    } else {
      items.push('Đảo ngược giãn cơ: Sugammadex ưu tiên khi suy thận (không tích lũy) · Neostigmine thận trọng')
    }

    // PONV
    const highPONV =
      patient.sex === 'female' ||
      patient.ageYears < 50 ||
      comorbidities.some((c) => c.conditionId === 'severe-ponv')

    if (highPONV) {
      items.push('Dự phòng PONV: Ondansetron 4–8 mg IV + Dexamethasone 4–8 mg IV trong mổ · 2 yếu tố nguy cơ trở lên')
    } else {
      items.push('Dự phòng PONV: Ondansetron 4 mg IV trước khi kết thúc mổ')
    }

    items.push('Rút nội khí quản khi: tỉnh hoàn toàn, tuân theo lệnh, SpO₂ ổn định, bảo vệ đường thở')

    if (input.surgery.airwayDifficulty === 'difficult') {
      items.push('⚠️ Đường thở khó — rút NKQ cẩn thận: có sẵn thiết bị tái đặt NKQ, xem xét rút NKQ qua AEC (airway exchange catheter)')
    }

  } else if (anaesthesiaType === 'neuraxial') {
    items.push('Chờ hết tê hoàn toàn trước khi chuyển bệnh nhân về phòng hồi tỉnh')
    items.push('Kiểm tra cảm giác và vận động trước khi cho đứng dậy (phòng hạ huyết áp tư thế)')

  } else if (anaesthesiaType === 'mac') {
    items.push('Giảm an thần từ từ · cho thở O₂ qua canula mũi đến khi SpO₂ ổn định phòng không')
    items.push('Tiêu chí xuất phòng PACU: MEDS score ≥ 12 hoặc Aldrete score ≥ 9')
  }

  return { title: 'Thoát mê & Rút nội khí quản', items }
}

function buildPostOpSection(input: PlanInput): PlanSection {
  const { surgery, comorbidities } = input
  const items: string[] = []

  // Giảm đau
  const isHighPain = surgery.painLevel === 'severe'
  const isModPain = surgery.painLevel === 'moderate'

  if (isHighPain) {
    items.push('Giảm đau đa mô thức: Paracetamol 15 mg/kg IV q6h + NSAID (Ketorolac 30 mg IV q8h nếu không CCĐ) + Opioid PCA (Morphine/Fentanyl)')
    items.push('Cân nhắc tê vùng liên tục (catheter) cho phẫu thuật đau nhiều: ngoài màng cứng ngực/thắt lưng, TAP block')
  } else if (isModPain) {
    items.push('Giảm đau: Paracetamol 500–1000 mg uống q6h ± NSAID đường uống · Tramadol 50–100 mg IV/PO PRN')
  } else {
    items.push('Giảm đau: Paracetamol 500–1000 mg uống q6h · NSAIDs nếu không chống chỉ định')
  }

  // Chống huyết khối
  if (surgery.durationMax > 60 && !['ophthalmology', 'endoscopy'].includes(input.surgery.specialtyId)) {
    items.push('Dự phòng huyết khối (DVT): vận động sớm + LMWH bắt đầu 12–24h sau mổ (cân nhắc CCĐ xuất huyết) + vớ áp lực')
  }

  // ICU
  const needsICU =
    input.isEmergency ||
    comorbidities.some((c) => c.asaMinimum >= 'IV') ||
    ['massive', 'high'].includes(surgery.bloodLoss) ||
    surgery.specialtyId === 'cardiac' ||
    surgery.specialtyId === 'neurosurgery'

  if (needsICU) {
    items.push('⚠️ Theo dõi sau mổ tại ICU/HDU — tiêu chí: ca cấp cứu, mất máu nhiều, ASA IV, phẫu thuật tim/thần kinh')
  } else {
    items.push('Theo dõi tại phòng PACU ≥ 1h trước chuyển về phòng bệnh')
  }

  // Phục hồi chức năng sớm (ERAS)
  if (!input.isEmergency && ['elective'].includes(surgery.urgency)) {
    items.push('ERAS: cho ăn uống sớm (nếu không có CCĐ tiêu hóa) · vận động nhẹ trong 6h đầu')
  }

  return { title: 'Chăm sóc sau mổ', items }
}

function collectWarnings(input: PlanInput, anaesthesiaType: AnaesthesiaType): string[] {
  const warnings: string[] = []
  const { comorbidities, surgery, patient } = input

  // Sốt ác tính
  if (comorbidities.some((c) => c.conditionId === 'malignant-hyperthermia')) {
    warnings.push('NGUY CƠ SỐT ÁC TÍNH — Tuyệt đối tránh Succinylcholine và thuốc mê bốc hơi (Halothane, Sevoflurane, Desflurane, Isoflurane). Dùng TIVA (Propofol + Remifentanil). Chuẩn bị Dantrolene ngay.')
  }

  // Dị ứng thuốc tê
  const latexAllergy = comorbidities.some((c) => c.conditionId === 'latex-allergy') ||
    patient.allergies.some((a) => a.toLowerCase().includes('latex'))
  if (latexAllergy) {
    warnings.push('DỊ ỨNG LATEX — Phòng mổ không latex (latex-free OR): găng tay, ống xông, mặt nạ không có latex. Thông báo tất cả nhân viên.')
  }

  // Nhược cơ
  if (comorbidities.some((c) => c.conditionId === 'myasthenia-gravis')) {
    warnings.push('NHƯỢC CƠ — Cực kỳ nhạy cảm với giãn cơ không khử cực. Tránh giãn cơ hoặc giảm liều tối thiểu. TOF monitoring bắt buộc. Có thể cần thở máy kéo dài sau mổ.')
  }

  // Pheochromocytoma
  if (comorbidities.some((c) => c.conditionId === 'pheochromocytoma')) {
    warnings.push('U TỦY THƯỢNG THẬN — Nguy cơ bão huyết áp trong mổ. Tránh kích thích gây tăng catecholamine. Chuẩn bị Phentolamine/Nicardipine IV sẵn.')
  }

  // Cấp cứu với dạ dày đầy
  if (input.isEmergency) {
    warnings.push('PHẪU THUẬT CẤP CỨU — Giả định dạ dày đầy. Bắt buộc RSI (tiền oxy hóa → Succinylcholine/Rocuronium liều cao → Ấn sụn nhẫn → NKQ). Không dùng mask bag-valve nếu có thể tránh.')
  }

  // Đường thở khó
  if (surgery.airwayDifficulty === 'difficult' || comorbidities.some((c) => c.conditionId === 'difficult-airway')) {
    warnings.push('ĐƯỜNG THỞ KHÓ DỰ KIẾN — Gọi thêm người hỗ trợ. Chuẩn bị: Video laryngoscope, fiberoptic, LMA cứu nạn, bougie. Theo dõi "cannot intubate cannot oxygenate" protocol.')
  }

  // LMWH/Warfarin và tê trục thần kinh
  if (
    anaesthesiaType === 'neuraxial' &&
    comorbidities.some((c) =>
      c.categoryId === 'hematologic' &&
      c.drugCautions.some((d) => d.toLowerCase().includes('kháng đông')),
    )
  ) {
    warnings.push('THUỐC KHÁNG ĐÔNG + TÊ TRỤC THẦN KINH — Nguy cơ tụ máu ngoài màng cứng/khoang tủy. Kiểm tra thời gian ngừng thuốc theo hướng dẫn ASRA trước khi tiến hành.')
  }

  return warnings
}

// ─── Entry point ──────────────────────────────────────────────────────────────

export function generateAnaestheticPlan(input: PlanInput): GeneratedPlan {
  const asaClass = resolveASAClass(input.comorbidities)
  const anaesthesiaType = resolveAnaesthesiaType(input)

  const sections: PlanSection[] = [
    buildPatientSummarySection(input, asaClass),
    buildPreOpSection(input),
    buildPremedSection(input),
    buildInductionSection(input, anaesthesiaType),
    buildMaintenanceSection(input, anaesthesiaType),
    buildMonitoringSection(input, anaesthesiaType),
    buildEmergenceSection(input, anaesthesiaType),
    buildPostOpSection(input),
  ]

  // Thêm lưu ý từ comorbidities vào section cuối
  const comorbiditySections = input.comorbidities.flatMap((c) =>
    c.anaesthesiaConsiderations.length > 0
      ? [{ title: `Lưu ý: ${c.conditionNameVn}`, items: c.anaesthesiaConsiderations }]
      : [],
  )
  sections.push(...comorbiditySections)

  // Thêm lưu ý từ phẫu thuật
  if (input.surgery.considerations.length > 0) {
    sections.push({
      title: 'Lưu ý đặc thù phẫu thuật',
      items: input.surgery.considerations,
      level: 'caution',
    })
  }

  const warnings = collectWarnings(input, anaesthesiaType)

  return {
    anaesthesiaType,
    anaesthesiaTypeLabel: ANAESTHESIA_LABEL[anaesthesiaType],
    asaClass,
    sections,
    warnings,
    generatedAt: Date.now(),
    isAiGenerated: false,
  }
}
